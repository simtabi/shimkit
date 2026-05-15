# shimkit ssh

SSH key + agent + known_hosts + perms hygiene. No third-party deps —
every operation shells out to baseline `ssh-keygen`, `ssh-add`,
`ssh-agent`, or `ssh`. Passphrases are never handled by shimkit:
`ssh-keygen` prompts the user directly.

Pure scanner logic lives in `src/shimkit/tools/ssh/scanner.py`
(filesystem read + known_hosts parser + perms audit). The manager
owns CommandRunner shell-outs.

## Commands

| Command                                          | Purpose                                                |
|--------------------------------------------------|--------------------------------------------------------|
| `shimkit ssh`                                    | Interactive menu (read-only paths only).               |
| `shimkit ssh keys list`                          | List every recognised private key.                     |
| `shimkit ssh keys generate NAME`                 | Generate a new key (MODERATE).                         |
| `shimkit ssh keys rotate NAME`                   | Back up the old key + regenerate (MODERATE).           |
| `shimkit ssh agent status`                       | Show ssh-agent state + loaded keys.                    |
| `shimkit ssh agent add KEY`                      | Pass-through to `ssh-add`.                             |
| `shimkit ssh known-hosts audit`                  | Find duplicate entries.                                |
| `shimkit ssh known-hosts prune`                  | Remove later duplicates (MODERATE).                    |
| `shimkit ssh perms audit`                        | Check ~/.ssh modes against the config matrix.          |
| `shimkit ssh perms fix`                          | chmod every offender (MODERATE).                       |
| `shimkit ssh config show [HOST]`                 | Print ~/.ssh/config; with HOST, expand via `ssh -G`.   |

Universal flags (`--quiet`, `--verbose`, `--log-file`, `--no-color`,
`--color`, `--no-input`) go before any subcommand. Per-command flags
(`--dry-run`, `--yes`, `--force`, `--json`, `--ssh-dir`,
`--type`, `--comment`) go after.

## Keys

```bash
shimkit ssh keys list                                # list every recognised key
shimkit ssh keys list --json                         # machine-readable

shimkit ssh keys generate id_work --type ed25519 --yes
shimkit ssh keys generate id_work -C work@example   # custom comment
shimkit ssh keys generate id_work --dry-run         # show command without running

shimkit ssh keys rotate id_ed25519 --yes            # backup + regenerate
```

`rotate` moves the old key to `<name>.bak-YYYYMMDDHHMMSS` and the old
`.pub` alongside, then runs `ssh-keygen` for a fresh pair. You're
responsible for syncing the new public key to your authorized_keys
on each server — shimkit prints the steps but pushes nowhere.

## ssh-agent

```bash
shimkit ssh agent status            # what's loaded
shimkit ssh agent status --json     # parses cleanly
shimkit ssh agent add ~/.ssh/id_ed25519
```

`status` differentiates "agent not running" (exit 1, warning) from
"agent running, no keys" (exit 0, info).

## known_hosts hygiene

```bash
shimkit ssh known-hosts audit --json
shimkit ssh known-hosts prune --yes
```

`audit` reports any `(host, key_blob)` pair seen more than once.
`prune` keeps the first occurrence and drops the rest; comments and
blank lines are preserved verbatim.

## Permission matrix

`audit` flags any path whose mode is **laxer** than the configured
expected mode. Stricter modes pass — a `0400` key is fine even though
expected is `600`.

Default matrix (`tools.ssh.perms`):

| Path                       | Expected |
|----------------------------|----------|
| `~/.ssh` (the dir)         | `700`    |
| Private keys               | `600`    |
| `.pub` files               | `644`    |
| `~/.ssh/config`            | `644`    |
| `~/.ssh/known_hosts`       | `644`    |
| `~/.ssh/authorized_keys`   | `644`    |

```bash
shimkit ssh perms audit --json     # report only
shimkit ssh perms fix --yes        # chmod each offender
shimkit ssh perms fix --dry-run    # what would change
```

## ~/.ssh/config

```bash
shimkit ssh config show              # print ~/.ssh/config verbatim
shimkit ssh config show gh           # `ssh -G gh` — effective expansion
```

The effective-expansion form is useful when `Include`s + multiple
`Host` blocks make it non-obvious what options actually apply.

## Configuration

```json
{
  "tools": {
    "ssh": {
      "ssh_dir": "~/.ssh",
      "default_key_type": "ed25519",
      "perms": {
        "dir": "700",
        "private_key": "600",
        "public_key": "644",
        "config": "644",
        "known_hosts": "644",
        "authorized_keys": "644"
      }
    }
  }
}
```

`--ssh-dir PATH` overrides `ssh_dir` for one invocation — used by
tests, also useful for editing a chroot's keys from outside.

## Exit codes

| Code | Meaning                                                     |
|-----:|-------------------------------------------------------------|
| 0    | success / no-op                                             |
| 1    | generic failure (overwrite refused, ssh-keygen non-zero, prompt cancelled, agent unreachable) |
| 2    | Typer usage error                                           |
| 69   | EX_UNAVAILABLE — wrong platform                             |
| 130  | SIGINT                                                      |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | ✓ — OpenSSH 9.x ships with macOS; `ssh-keygen` / `ssh-add` baseline. |
| Linux    | ✓ — `openssh-client` package, also baseline.                          |
| WSL      | ✓ (Linux path).                                                       |
| Windows  | ✗ — out of charter.                                                   |

## Security notes

- **Passphrases never pass through shimkit.** `ssh-keygen` reads them
  interactively from the TTY; our `CommandRunner.run` call uses
  `capture_output=False` for that step. Nothing involving the
  passphrase is logged, captured, or echoed.
- **No automatic key push.** `keys rotate` does *not* upload the new
  public key anywhere. You sync `authorized_keys` on each server
  yourself.
- **`config show` is read-only.** `~/.ssh/config` is your domain;
  shimkit reads it but doesn't write to it.
