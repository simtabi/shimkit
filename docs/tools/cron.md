# shimkit cron

Generic user-crontab editor. Manages entries identified by a
`# shimkit:<name>` comment immediately above the schedule line.
User-authored entries are never touched.

Atomic write: every mutator builds the new crontab in memory, writes
it to a tempfile, then `crontab <tempfile>`. The user's previous
crontab is backed up to `~/.shimkit/data/cron/crontab-YYYY...bak`
before the write, so `shimkit cron rollback` is a one-command undo.

## Commands

| Command                                     | Purpose                                                         |
|---------------------------------------------|-----------------------------------------------------------------|
| `shimkit cron`                              | Menu.                                                           |
| `shimkit cron show [--json]`                | Print the entire user crontab (shimkit-managed + user-authored).|
| `shimkit cron list [--json]`                | List shimkit-managed entries only.                              |
| `shimkit cron add --name N --schedule S --cmd C [--comment T]` | MODERATE. Add a marker + schedule line.    |
| `shimkit cron remove NAME`                  | MODERATE. Drop both the marker and the schedule line for NAME.  |
| `shimkit cron rollback`                     | MODERATE. Restore the latest backup over the current crontab.   |

Universal flags before the subcommand (`--quiet`, `--verbose`,
`--log-file`, `--no-color`, `--color`, `--no-input`); per-command
flags after (`--json`, `--dry-run`, `--yes`, `--force`).

## Schedule syntax

`--schedule` accepts:

- The seven `@`-shorthands: `@reboot`, `@yearly` / `@annually`,
  `@monthly`, `@weekly`, `@daily`, `@hourly`.
- Five-field cron expressions: `<minute> <hour> <dom> <month> <dow>`.
  Each field can hold digits, `*`, `,`-separated lists, `-`-ranges,
  `/`-steps, and (for month/dow) three-letter names.

shimkit does **structural** validation only — empty input, missing
fields, mistyped `@nonsense` — and refuses up-front. Semantic
validation (numeric ranges, alphabetic name validity) is left to
`cron`; if `cron` rejects the loaded file, shimkit surfaces its
error text. The backup means a bad `add` is one `rollback` away.

## Examples

```bash
# Show what's in the crontab right now
shimkit cron show

# Add a nightly backup
shimkit cron add --yes \
    --name backup \
    --schedule "0 3 * * *" \
    --cmd "/usr/local/bin/dump.sh" \
    --comment "nightly DB dump"

# Add an @hourly log rotation
shimkit cron add --yes \
    --name rotate \
    --schedule @hourly \
    --cmd "/opt/log/rotate.sh"

# List only the things shimkit manages
shimkit cron list
shimkit cron list --json

# Preview what would land without writing
shimkit cron add --yes --dry-run \
    --name probe --schedule @daily --cmd /bin/true

# Drop one entry by name (leaves user-authored cron lines alone)
shimkit cron remove backup --yes

# Got into a bad state? Restore the most recent backup.
shimkit cron rollback --yes
```

## On-disk format

After `shimkit cron add --name backup --schedule "0 3 * * *" --cmd "/usr/local/bin/dump.sh" --comment "nightly DB dump"`:

```
# user-authored noise stays untouched
@reboot /opt/legacy/startup.sh

# shimkit:backup nightly DB dump
0 3 * * * /usr/local/bin/dump.sh
```

The two-line block is what shimkit identifies as managed. Editing
either line by hand is fine — `shimkit cron list` will keep
finding it as long as the marker comment is exactly one line above
the schedule line. The free-text comment after the marker name is
optional and is preserved on round-trip.

## JSON output

```bash
$ shimkit cron list --json
{
  "ts": "...",
  "tool": "cron",
  "step": "list",
  "status": "ok",
  "data": {
    "entries": [
      {
        "name": "backup",
        "schedule": "0 3 * * *",
        "command": "/usr/local/bin/dump.sh",
        "comment": "nightly DB dump"
      }
    ]
  }
}
```

`shimkit cron show --json` returns the entire crontab body in
`data.body` (one string), useful for piping into a diff or backup
process.

## Configuration

```json
{
  "tools": {
    "cron": {
      "managed_prefix": "# shimkit:",
      "backup_dir": "~/.shimkit/data/cron",
      "max_managed_entries": 200
    }
  }
}
```

`managed_prefix` is the literal string that identifies a shimkit-
managed entry — change it if you'd rather use `# my-org:` or a
different marker. The `max_managed_entries` cap (default 200) is
shimkit refusing to install more entries than the limit; tune up
or down in your user config.

## Exit codes

| Code | Meaning                                                       |
|-----:|---------------------------------------------------------------|
| 0    | success / no-op (entry missing on remove, etc.)               |
| 1    | invalid name / invalid schedule / empty command / duplicate name / cap hit / prompt cancelled |
| 2    | Typer usage error                                             |
| 69   | EX_UNAVAILABLE — wrong platform or `crontab` not on PATH      |
| 130  | SIGINT                                                        |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | ✓ — `crontab(1)` ships with the system; the user crontab lives at `/var/at/tabs/<user>` (read via `crontab -l`). |
| Linux    | ✓ — `cron` (Debian/Ubuntu) or `cronie` (RHEL); user crontab at `/var/spool/cron/crontabs/<user>` (read via `crontab -l`). |
| WSL      | ✓ (Linux path); note that cron daemon isn't running by default on WSL — start with `sudo service cron start`. |
| Windows  | ✗ — out of charter (Windows uses Task Scheduler, not cron). |

## Charter notes

The source ubuntu `add:cron.sh` was Laravel-specific (hardcoded
`php artisan schedule:run`). `shimkit cron` is the generic
host-side editor — bring your own schedule and command. Application
frameworks can layer on top by passing their schedule + command
through this surface; that's a v0.7+ candidate (`shimkit framework
laravel cron-install`).
