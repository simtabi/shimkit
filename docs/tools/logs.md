# shimkit logs

Tail / grep the system log on the host machine. Read-only — no
mutators, no prompts. macOS routes through `log show` / `log
stream` (Apple's Unified Logging — the Console.app data source);
Linux routes through `journalctl`.

Predicate syntax is **not translated** between platforms. Each
binary has its own filter language and trying to abstract them
would be a leaky abstraction. Read the docs for whichever you're
on:

- **macOS** — NSPredicate-style, e.g.
  `process == "kernel" AND eventMessage CONTAINS "wifi"`.
- **Linux** — `journalctl(1)` flags: `-p err`, `-u sshd`,
  `--grep PATTERN`, `--since "1 hour ago"`.

## Commands

| Command                                            | Purpose                                                       |
|----------------------------------------------------|---------------------------------------------------------------|
| `shimkit logs`                                     | Interactive menu (tail / errors).                             |
| `shimkit logs tail [--lines N] [--follow] [--predicate P]` | Show the last N log lines.                            |
| `shimkit logs grep PATTERN [--since DUR] [--unit U]`       | Search log history for PATTERN.                       |
| `shimkit logs system show [--priority LVL]`        | Recent system log filtered by priority.                       |

Universal flags (`--quiet`, `--verbose`, `--log-file`, `--no-color`,
`--color`, `--no-input`) go before the subcommand. Per-command flags
(`--json`, `--lines`, `--follow`, `--predicate`, `--unit`,
`--since`, `--priority`) go after.

## Examples

```bash
# Show the last 200 log lines
shimkit logs tail --lines 200

# Follow new entries in real time
shimkit logs tail --follow

# Only entries from sshd (Linux)
shimkit logs tail --unit sshd

# macOS: kernel-only with a predicate
shimkit logs tail --predicate 'process == "kernel"'

# Linux: filter by regex pattern (passed to journalctl --grep)
shimkit logs tail --predicate 'auth.*fail'

# Grep history (default window: 1 hour)
shimkit logs grep "Connection refused"
shimkit logs grep "Connection refused" --since 24h          # macOS
shimkit logs grep "Connection refused" --since "24 hours ago"  # Linux

# Errors and worse
shimkit logs system show --priority error        # macOS
shimkit logs system show --priority err          # Linux journalctl form
```

## `--json` mode

`--json` short-circuits the shell-out and emits the argv list that
*would* run. Useful for previewing what a flag combination produces
without burning a real journal read.

```bash
$ shimkit logs tail --unit sshd --lines 10 --json
{
  "ts": "...",
  "tool": "logs",
  "step": "tail",
  "status": "ok",
  "data": {
    "platform": "Linux",
    "args": ["journalctl", "-n", "10", "-u", "sshd"],
    "follow": false
  }
}
```

`--json` is also helpful in scripts that want to use shimkit as a
predicate-translator for one platform's CLI from another (e.g.
generating the right `journalctl` argv from a Mac-shaped invocation
for use in a CI script).

## Configuration

```json
{
  "tools": {
    "logs": {
      "default_lines": 100,
      "max_grep_lines": 5000
    }
  }
}
```

`max_grep_lines` only applies on Linux's `journalctl`; macOS's `log
show` paginates internally and we don't second-guess it.

## Exit codes

| Code | Meaning                                                            |
|-----:|--------------------------------------------------------------------|
| 0    | success (incl. journalctl's "no match found" exit-1)               |
| 1    | underlying binary failed in a non-trivial way                      |
| 2    | Typer usage error                                                  |
| 69   | EX_UNAVAILABLE — wrong platform or `log` / `journalctl` not on PATH |
| 130  | SIGINT (typical exit for `tail --follow`)                          |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | ✓ — `log` ships preinstalled with macOS.                              |
| Linux    | ✓ — `journalctl` from systemd. On non-systemd distros, this tool is unavailable. |
| WSL      | Partial — works only if systemd is enabled in WSL2 (`systemd=true` in `/etc/wsl.conf`). |
| Windows  | ✗ — out of charter.                                                   |

## Read-only by design

There are no mutators here. No `--yes`, no `--force`, no `--confirm`
token, no MODERATE-tier prompt. The whole tool is a thin convenience
layer over two well-trusted vendor binaries. If you want to write
to the system log, use `logger(1)` directly.
