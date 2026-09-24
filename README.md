# envcheck

Lint `.env` files and compare them with a template (`.env.example`), offline. Standard library only, Python 3.9+.

**It never prints a value**, only key names and line numbers, so its output is safe to paste into a ticket or a CI log even when the file holds secrets.

```
$ python -m envcheck tests/data/messy.env --template tests/data/example.env
tests/data/messy.env: 11 variables, 18 findings
  error [missing] SMTP_URL is in the template (line 6) but not in the .env file
  warn  line 3 [spaces] space before '=' after 'DB_HOST'; some loaders reject or keep it in the key
  warn  line 4 [placeholder] DB_PASSWORD still looks like a placeholder value
  info  line 5 [empty] API_KEY is empty
  warn  line 7 [duplicate] DEBUG is defined again (first on line 6); the last one usually wins
  error line 11 [syntax] no '=' in this line (expected KEY=value)
  error line 12 [key] '2FAST' is not a valid variable name (letters, digits and _, not starting with a digit)
  error line 16 [quote] UNCLOSED starts a double-quoted value that is never closed
  ...
4 errors, 6 warnings
```

## Usage

```
python -m envcheck .env [--template .env.example] [--json] [--strict] [--quiet]
```

Exit code `0` if there are no errors, `1` for errors (or warnings with `--strict`), `2` if a file can't be read. `--quiet` hides info-level findings.

## What it checks

| Rule | Level | Finding |
| --- | --- | --- |
| `syntax`, `key` | error | a line without `=`; a name that is not letters, digits and `_` or starts with a digit |
| `quote` | error / warn | a quoted value that is never closed; text after the closing quote |
| `missing` | error | a key in the template that the `.env` file lacks |
| `extra` | info | a key in the `.env` file that the template does not list |
| `duplicate` | warn | the same key defined twice |
| `placeholder` | warn | a value like `changeme`, `your_api_key_here`, `xxxx`, `<token>`, `TODO` in the real file (not in the template) |
| `spaces` | warn | spaces around `=`, which some loaders keep as part of the key or value |
| `unquoted` | warn | spaces in an unquoted value |
| `comment` | info | a ` #` comment on a value line, which not every loader strips |
| `empty`, `case`, `trailing` | info | an empty value; a lower-case name; trailing whitespace |
| `bom` | warn | a byte-order mark at the start |

It understands `export KEY=value`, single and double quotes, `\"` inside double quotes, and quoted values that span several lines. Problems in the template itself (other than info-level ones) are reported too, marked `[template]`.

## What it does not do

- Different loaders (`python-dotenv`, Docker Compose, shells, `dotenv` for Node) disagree about quoting, comments and variable expansion. It flags the ambiguous cases and does not pick one loader's rules; it does not expand `${VAR}` references.
- It does not judge whether a value is correct or a secret is strong, and does not scan for leaked secrets. Placeholder detection is a short list of obvious patterns.

## Tests

```
python -m unittest discover -s tests -v
```

MIT licence.
