# shimkit hosts

`/etc/hosts` editor with atomic-write + timestamped backups. Same
atomic-replace pattern as `adguard.resolv.write_resolv_static`: write
to a temp file, then `sudo install -m 0644 -o root <tmp> /etc/hosts`.
Bind-mounted hosts files (typical inside containers) fall through to a
Python direct-write through the existing inode.

Pure parsing + mutation logic lives in
`src/shimkit/tools/hosts/editor.py` (no I/O), so the model is
unit-testable without touching the system hosts file.

## Commands

| Command                                | Purpose                                                            |
|----------------------------------------|--------------------------------------------------------------------|
| `shimkit hosts`                        | Interactive menu (list / rollback).                                |
| `shimkit hosts show`                   | Print every entry.                                                 |
| `shimkit hosts add IP NAME`            | Append. Idempotent. MODERATE prompt.                               |
| `shimkit hosts remove NAME`            | Remove every entry whose hostname matches. MODERATE prompt.        |
| `shimkit hosts block DOMAIN`           | Alias for `add 127.0.0.1 DOMAIN`.                                  |
| `shimkit hosts unblock DOMAIN`         | Alias for `remove DOMAIN`.                                         |
| `shimkit hosts apply-list SOURCE`      | Apply a StevenBlack-style list. **SEVERE** — token required.       |
| `shimkit hosts rollback`               | Restore the most recent backup.                                    |

`SOURCE` for `apply-list` is either `http(s)://...` (fetched via
stdlib `urllib.request`, no extra deps) or a local file path.

Universal flags (`--quiet`, `--verbose`, `--log-file`, `--no-color`,
`--color`, `--no-input`) go before the subcommand. Per-command flags
(`--dry-run`, `--yes`, `--force`, `--confirm`, `--path`) go after.

## Safety + the SEVERE tier

`apply-list` is the only severe-tier command. It can write thousands
of entries at once, so the default token is `APPLY-LIST`:

```bash
shimkit hosts apply-list https://example.com/list.txt --confirm APPLY-LIST
```

The size cap (`tools.hosts.max_entries_per_apply`, default `5000`)
refuses lists bigger than the threshold. Raise it in
`~/.config/shimkit/shimkit.json` if you really want the full
StevenBlack-extended list.

`add` / `remove` / `block` / `unblock` are MODERATE-tier — they
prompt `[y/N]` by default; `--yes` / `--force` skip; `--no-input`
refuses with exit 1.

## Atomic-write + backup

Every mutator follows the same sequence:

1. Parse the current file.
2. Compute the new content in-memory.
3. `sudo cp -a /etc/hosts /etc/hosts.bak-YYYYMMDDHHMMSS`.
4. Write to a temp file, then `sudo install -m 0644 -o root` over
   the target.
5. If `install` fails (typical inside container bind-mounts), fall
   back to a Python direct-write through the existing inode —
   requires the process is already root.

`rollback` restores the latest `*.bak-*` file.

## JSON output

```bash
$ shimkit hosts show --json
{
  "ts": "...",
  "tool": "hosts",
  "step": "show",
  "status": "ok",
  "data": {
    "path": "/etc/hosts",
    "entries": [
      {"ip": "127.0.0.1", "name": "localhost", "comment": null},
      {"ip": "::1", "name": "localhost", "comment": null}
    ]
  }
}
```

## Configuration

```json
{
  "tools": {
    "hosts": {
      "hosts_path": "/etc/hosts",
      "apply_list_severe_token": "APPLY-LIST",
      "max_entries_per_apply": 5000,
      "managed_block_marker": "# === shimkit-managed ==="
    }
  }
}
```

`--path PATH` overrides `hosts_path` for one invocation — useful for
testing or for editing a chroot's hosts file from outside.

## Exit codes

| Code | Meaning                                              |
|-----:|------------------------------------------------------|
| 0    | success / no-op (entry already present / not present)|
| 1    | generic failure (invalid IP, no backup, prompt cancelled, severe-token missing) |
| 2    | Typer usage error                                    |
| 69   | EX_UNAVAILABLE — wrong platform or hosts file missing |
| 130  | SIGINT                                               |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | ✓ — `/etc/hosts` lives in the same place; same atomic-replace path. |
| Linux    | ✓                                                                   |
| WSL      | ✓ (Linux path).                                                     |
| Windows  | ✗ — out of charter.                                                 |
