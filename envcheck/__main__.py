import argparse
import json
import sys

from . import compare, lint


def read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="envcheck", description="Lint a .env file and compare it with a template. Values are never printed.")
    ap.add_argument("envfile", help="the .env file")
    ap.add_argument("--template", help="the .env.example (or similar) to compare with")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    ap.add_argument("--quiet", action="store_true", help="hide info-level findings")
    args = ap.parse_args(argv)
    try:
        real, findings = lint(read(args.envfile))
        if args.template:
            tpl, tfind = lint(read(args.template), is_template=True)
            findings += compare(real, tpl)
            findings += [type(f)(f.level, f.line, f.rule, "[template] " + f.message) for f in tfind if f.level != "info"]
    except OSError as exc:
        print("envcheck: cannot read %s: %s" % (exc.filename, exc.strerror), file=sys.stderr)
        return 2
    findings = [f for f in findings if not (args.quiet and f.level == "info")]
    findings.sort(key=lambda f: (f.line or 0, f.rule))
    errors = sum(f.level == "error" for f in findings)
    warnings = sum(f.level == "warn" for f in findings)
    if args.json:
        print(json.dumps({"variables": len(real), "findings": [{"level": f.level, "line": f.line, "rule": f.rule, "message": f.message} for f in findings]}, indent=2))
    else:
        print("%s: %d variables, %d findings" % (args.envfile, len(real), len(findings)))
        for f in findings:
            print("  %-5s%s [%s] %s" % (f.level, "" if f.line is None else " line %d" % f.line, f.rule, f.message))
        print("%d errors, %d warnings" % (errors, warnings))
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
