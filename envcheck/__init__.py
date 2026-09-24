"""Lint .env files and compare them with a template, offline. Values are never printed, only key names and line numbers."""
import re

KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PLACEHOLDER = re.compile(r"^(changeme|change_me|change-me|your[_-].*|xxx+|todo|tbd|replace[_-]?me|example|<.*>|\.\.\.|secret|password|test)$", re.I)


class Finding:
    def __init__(self, level, line, rule, message):
        self.level, self.line, self.rule, self.message = level, line, rule, message

    def __repr__(self):
        return "%s%s [%s]: %s" % (self.level, "" if self.line is None else " line %d" % self.line, self.rule, self.message)


def parse(text):
    """Returns (entries, findings). Each entry is (key, value, line number, quote character or '')."""
    entries, findings = [], []
    lines = text.split("\n")
    if text.startswith("﻿"):
        findings.append(Finding("warn", 1, "bom", "the file starts with a byte-order mark; the first key may be read with an invisible prefix"))
        lines[0] = lines[0][1:]
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip("\r")
        n = i + 1
        i += 1
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            findings.append(Finding("error", n, "syntax", "no '=' in this line (expected KEY=value)"))
            continue
        key, _, rest = line.partition("=")
        if key != key.rstrip():
            findings.append(Finding("warn", n, "spaces", "space before '=' after %r; some loaders reject or keep it in the key" % key.strip()))
        key = key.strip()
        if rest.startswith(" ") and rest.strip():
            findings.append(Finding("warn", n, "spaces", "space after '=' for %s; some loaders keep it as part of the value" % key))
        rest = rest.lstrip()
        if not KEY.match(key):
            findings.append(Finding("error", n, "key", "%r is not a valid variable name (letters, digits and _, not starting with a digit)" % key))
            continue
        quote = rest[:1] if rest[:1] in ("'", '"') else ""
        value = rest
        if quote:
            end = -1
            j = 1
            while j < len(rest):
                if rest[j] == "\\" and quote == '"':
                    j += 2
                    continue
                if rest[j] == quote:
                    end = j
                    break
                j += 1
            if end == -1:
                # a quoted value may continue over several lines
                buf = rest[1:]
                closed = False
                while i < len(lines):
                    nxt = lines[i].rstrip("\r")
                    i += 1
                    if quote in nxt:
                        buf += "\n" + nxt[:nxt.index(quote)]
                        closed = True
                        break
                    buf += "\n" + nxt
                if not closed:
                    findings.append(Finding("error", n, "quote", "%s starts a %s-quoted value that is never closed" % (key, "double" if quote == '"' else "single")))
                    continue
                value = buf
            else:
                value = rest[1:end]
                after = rest[end + 1:].strip()
                if after and not after.startswith("#"):
                    findings.append(Finding("warn", n, "quote", "text after the closing quote of %s is ignored or an error, depending on the loader" % key))
        else:
            hash_at = re.search(r"\s#", rest)
            if hash_at:
                findings.append(Finding("info", n, "comment", "%s has a ' #' comment on the value line; not every loader strips it, so quote the value if the # is part of it" % key))
                value = rest[:hash_at.start()]
            value = value.rstrip()
            if " " in value:
                findings.append(Finding("warn", n, "unquoted", "%s has spaces in an unquoted value; quote it to be safe across loaders" % key))
            if value != rest and not hash_at:
                findings.append(Finding("info", n, "trailing", "%s has trailing whitespace after the value" % key))
        entries.append((key, value, n, quote))
    return entries, findings


def lint(text, is_template=False):
    entries, findings = parse(text)
    seen = {}
    for key, value, n, quote in entries:
        if key in seen:
            findings.append(Finding("warn", n, "duplicate", "%s is defined again (first on line %d); the last one usually wins" % (key, seen[key])))
        seen.setdefault(key, n)
        if key != key.upper():
            findings.append(Finding("info", n, "case", "%s is not upper-case; the convention is UPPER_SNAKE_CASE" % key))
        if not is_template:
            if value == "":
                findings.append(Finding("info", n, "empty", "%s is empty" % key))
            elif PLACEHOLDER.match(value.strip()):
                findings.append(Finding("warn", n, "placeholder", "%s still looks like a placeholder value" % key))
    return entries, findings


def compare(real, template):
    """Findings for keys missing from the real file, and for keys the template does not list."""
    have = {k for k, *_ in real}
    want = {k for k, *_ in template}
    out = []
    for k, _, n, _ in template:
        if k not in have:
            out.append(Finding("error", None, "missing", "%s is in the template (line %d) but not in the .env file" % (k, n)))
    for k, _, n, _ in real:
        if k not in want:
            out.append(Finding("info", n, "extra", "%s is in the .env file but not in the template" % k))
    return out
