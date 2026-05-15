# shimkit env

`.env` file viewer + scaffolder with secret redaction. Default-deny
on values: a key whose name matches a secret-fragment regex (the same
one the JSONL logger uses) is rendered as `KEY=********` until you
opt in with `--reveal`.

Pure parser in `src/shimkit/tools/env/parser.py` accepts the common
dotenv grammar (`KEY=value`, `KEY="quoted"`, `KEY='single'`,
`export KEY=...`, comments, blank lines, trailing `# comment`).
Variable interpolation (`${OTHER}`) is intentionally NOT supported —
that's a runtime concern for whichever dotenv loader your app uses.

## Commands

| Command                                | Purpose                                                          |
|----------------------------------------|------------------------------------------------------------------|
| `shimkit env`                          | Interactive menu (read-only paths).                              |
| `shimkit env show [PATH]`              | Print PATH (or auto-discovered .env) with secrets masked.        |
| `shimkit env show PATH --reveal`       | Same, but show secret values verbatim.                           |
| `shimkit env list [ROOT]`              | Walk ROOT (default cwd) for every `.env*` file.                  |
| `shimkit env scaffold PATH`            | Write a starter template at PATH. Refuses to overwrite.          |
| `shimkit env diff A B`                 | Compare key sets + values between two `.env` files.              |
| `shimkit env redact SRC DST`           | Write a redacted copy of SRC to DST.                             |

Universal flags (`--quiet`, `--verbose`, `--log-file`, `--no-color`,
`--color`, `--no-input`) go before any subcommand. Per-command flags
(`--json`, `--dry-run`, `--reveal`) go after.

## Auto-discovery

`shimkit env show` without an explicit path searches the cwd for the
first hit in `tools.env.default_search_paths`:

```
.env
.env.local
.env.development
.env.production
```

Override per-invocation by passing an explicit path; override the
search order project-wide via `~/.config/shimkit/shimkit.json`.

## Redaction

A key whose name matches `tools.env.redact_pattern` (default:
`password|passwd|pwd|secret|token|api[_-]?key|authorization|key|credential`,
case-insensitive substring match) is masked. The pattern is the same
shape used by `shimkit.core.log.redact_value` — what's a secret in
your JSONL logs is a secret here.

Masked output looks like:

```
APP_ENV=production
API_KEY=********    # was: "supersecret123"
DATABASE_PASSWORD=********
```

`--reveal` shows verbatim values. Use sparingly; the default-deny is
there to protect copy-paste accidents.

## Examples

```bash
shimkit env show                              # cwd auto-discovery, redacted
shimkit env show .env.production              # explicit path
shimkit env show .env.production --reveal     # show secrets
shimkit env show --json                       # parses cleanly

shimkit env list .                            # every .env* under cwd
shimkit env list . --json

shimkit env scaffold .env.local               # create from template
shimkit env scaffold .env --dry-run           # show without writing

shimkit env diff .env.example .env.production # what's missing locally?
shimkit env diff a b --json                   # machine-readable

shimkit env redact .env .env.redacted         # commit-safe copy
```

## JSON output

```bash
$ shimkit env show .env --json
{
  "ts": "...",
  "tool": "env",
  "step": "show",
  "status": "ok",
  "data": {
    "path": ".env",
    "reveal": false,
    "entries": [
      {"key": "APP_ENV", "value": "production", "redacted": false, "comment": null},
      {"key": "API_KEY", "value": "********",   "redacted": true,  "comment": null}
    ]
  }
}
```

`redacted: true` means the value was masked because the key matched
the secret pattern AND the value was non-empty.

## Configuration

```json
{
  "tools": {
    "env": {
      "redact_pattern": "password|passwd|pwd|secret|token|api[_-]?key|authorization|key|credential",
      "default_search_paths": [".env", ".env.local", ".env.development", ".env.production"]
    }
  }
}
```

## Exit codes

| Code | Meaning                                              |
|-----:|------------------------------------------------------|
| 0    | success / no-op                                      |
| 1    | not a file, no .env found, refusing to overwrite      |
| 2    | Typer usage error                                    |
| 69   | EX_UNAVAILABLE — wrong platform                       |
| 130  | SIGINT                                               |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | ✓                          |
| Linux    | ✓                          |
| WSL      | ✓ (Linux path).            |
| Windows  | ✗ — out of charter.        |
