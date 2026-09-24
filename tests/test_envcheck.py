import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import envcheck as ec
from envcheck.__main__ import main

MESSY = os.path.join(HERE, "data", "messy.env")
EXAMPLE = os.path.join(HERE, "data", "example.env")


def found(text, **kw):
    return [(f.level, f.line, f.rule) for f in ec.lint(text, **kw)[1]]


def values(text):
    return {k: v for k, v, _, _ in ec.parse(text)[0]}


class Parse(unittest.TestCase):
    def test_plain_quoted_and_export(self):
        v = values("A=1\nB='two words'\nC=\"three words\"\nexport D=4\n# comment\n\nE=\n")
        self.assertEqual(v, {"A": "1", "B": "two words", "C": "three words", "D": "4", "E": ""})

    def test_multiline_quoted_value(self):
        text = 'A="line one\nline two"\nB=2\n'
        entries = ec.parse(text)[0]
        self.assertEqual([(k, n) for k, _, n, _ in entries], [("A", 1), ("B", 3)])
        self.assertEqual(entries[0][1], "line one\nline two")

    def test_escaped_quote_inside_double_quotes(self):
        self.assertEqual(values('A="say \\"hi\\""\n'), {"A": 'say \\"hi\\"'})

    def test_equals_inside_value(self):
        self.assertEqual(values("URL=postgres://u:p@h/db?a=b\n")["URL"], "postgres://u:p@h/db?a=b")

    def test_crlf_lines(self):
        self.assertEqual(values("A=1\r\nB=2\r\n"), {"A": "1", "B": "2"})


class Lint(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(found("APP=demo\nPORT=8080\n"), [])

    def test_syntax_and_key_errors(self):
        self.assertEqual(found("NOEQUALS\n"), [("error", 1, "syntax")])
        self.assertEqual(found("1BAD=x\n"), [("error", 1, "key")])
        self.assertEqual(found("A-B=x\n"), [("error", 1, "key")])

    def test_unclosed_quote(self):
        self.assertEqual(found('A="oops\nB=2\n'), [("error", 1, "quote")])
        self.assertEqual(found("A='oops\n"), [("error", 1, "quote")])

    def test_spaces_around_equals(self):
        self.assertEqual(found("A = 1\n"), [("warn", 1, "spaces"), ("warn", 1, "spaces")])
        self.assertEqual(found("A =1\n"), [("warn", 1, "spaces")])
        self.assertEqual(found("A= 1\n"), [("warn", 1, "spaces")])
        self.assertEqual(found("A=\n"), [("info", 1, "empty")])

    def test_unquoted_spaces_and_comments(self):
        self.assertEqual(found("A=hello world\n"), [("warn", 1, "unquoted")])
        self.assertEqual(found('A="hello world"\n'), [])
        self.assertEqual(found("A=abc # note\n"), [("info", 1, "comment")])
        self.assertEqual(found('A="abc # not a comment"\n'), [])
        self.assertEqual(found("A=abc#no-space\n"), [])

    def test_text_after_closing_quote(self):
        self.assertEqual(found('A="x" y\n'), [("warn", 1, "quote")])
        self.assertEqual(found('A="x" # fine\n'), [])

    def test_duplicates(self):
        self.assertEqual(found("A=1\nA=2\n"), [("warn", 2, "duplicate")])

    def test_case(self):
        self.assertEqual(found("lower=1\n"), [("info", 1, "case")])

    def test_placeholders_only_in_real_files(self):
        for v in ("changeme", "CHANGE_ME", "your_api_key_here", "xxxx", "<token>", "TODO", "..."):
            self.assertEqual(found("KEY=%s\n" % v), [("warn", 1, "placeholder")], v)
        self.assertEqual(found("KEY=changeme\n", is_template=True), [])
        self.assertEqual(found("KEY=real-value-123\n"), [])

    def test_bom(self):
        self.assertEqual(found("﻿A=1\n"), [("warn", 1, "bom")])

    def test_values_are_never_in_messages(self):
        for f in ec.lint("SECRET=hunter2hunter2\nB=changeme\nC=two words\n")[1]:
            self.assertNotIn("hunter2", f.message)
            self.assertNotIn("changeme", f.message)


class Compare(unittest.TestCase):
    def test_missing_and_extra(self):
        real, _ = ec.lint("A=1\nB=2\nEXTRA=3\n")
        tpl, _ = ec.lint("A=\nB=\nC=\nD=\n", is_template=True)
        out = [(f.level, f.line, f.rule, f.message) for f in ec.compare(real, tpl)]
        self.assertEqual(out, [("error", None, "missing", "C is in the template (line 3) but not in the .env file"),
                               ("error", None, "missing", "D is in the template (line 4) but not in the .env file"),
                               ("info", 3, "extra", "EXTRA is in the .env file but not in the template")])

    def test_same_keys(self):
        real, _ = ec.lint("A=1\nB=2\n")
        tpl, _ = ec.lint("B=\nA=\n", is_template=True)
        self.assertEqual(ec.compare(real, tpl), [])


class Cli(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_messy_with_template(self):
        code, out, _ = self.run_cli(MESSY, "--template", EXAMPLE)
        self.assertEqual(code, 1)
        self.assertIn("11 variables, 18 findings", out)
        self.assertIn("error [missing] SMTP_URL is in the template (line 6) but not in the .env file", out)
        self.assertIn("4 errors, 6 warnings", out)

    def test_messy_never_prints_values(self):
        _, out, _ = self.run_cli(MESSY, "--template", EXAMPLE)
        self.assertNotIn("localhost", out)
        self.assertNotIn("changeme", out)

    def test_quiet_json_strict(self):
        self.assertNotIn("info ", self.run_cli(MESSY, "--quiet")[1])
        data = json.loads(self.run_cli(MESSY, "--json")[1])
        self.assertEqual(data["variables"], 11)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".env")
            with open(p, "w") as fh:
                fh.write("A=hello world\n")
            self.assertEqual(self.run_cli(p)[0], 0)
            self.assertEqual(self.run_cli(p, "--strict")[0], 1)

    def test_missing_files(self):
        code, _, err = self.run_cli("/no/such/.env")
        self.assertEqual(code, 2)
        self.assertIn("cannot read /no/such/.env", err)
        self.assertEqual(self.run_cli(MESSY, "--template", "/no/such")[0], 2)


if __name__ == "__main__":
    unittest.main()
