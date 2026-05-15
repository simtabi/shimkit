# shimkit gpg

GPG key + git-signing hygiene. No third-party deps — shells out to
the baseline `gpg` binary and `git`. Passphrases never pass through
shimkit: `gpg --quick-gen-key` reads them directly from the TTY.

Pure parsers in `src/shimkit/tools/gpg/parser.py` handle gpg's
`--with-colons` machine-readable format and `git config
--get-regexp` output.

## Commands

| Command                                                   | Purpose                                                       |
|-----------------------------------------------------------|---------------------------------------------------------------|
| `shimkit gpg`                                             | Interactive menu (read-only paths).                           |
| `shimkit gpg keys list`                                   | List every primary key in your keyring.                       |
| `shimkit gpg keys generate NAME EMAIL`                    | Generate a new key (MODERATE).                                |
| `shimkit gpg keys export KEY_ID [--dest PATH]`            | ASCII-armoured public-key export.                             |
| `shimkit gpg agent status`                                | Check whether gpg-agent is responding.                        |
| `shimkit gpg git-signing show`                            | Show current `user.signingkey` + `commit.gpgsign` config.      |
| `shimkit gpg git-signing configure KEY_ID [--scope SCOPE]`| Set the signing config (MODERATE).                            |

Universal flags (`--quiet`, `--verbose`, `--log-file`, `--no-color`,
`--color`, `--no-input`) go before the subcommand. Per-command flags
(`--json`, `--dry-run`, `--yes`, `--force`, `--type`, `--expiry`,
`--dest`, `--scope`) go after.

## Generating a key

```bash
shimkit gpg keys generate "Real Name" name@example.com --type ed25519 --yes
shimkit gpg keys generate "Real Name" name@example.com \
    --type rsa4096 --expiry 2y --yes
shimkit gpg keys generate "Real Name" name@example.com --dry-run
```

Allowed key types: `ed25519` (default), `rsa3072`, `rsa4096`.

Expiry is gpg's relative form (`1y`, `6m`, `0` for never). Default
is `1y` from `tools.gpg.default_key_expiry`.

When the command runs, gpg's pinentry prompts the user for a
passphrase directly. shimkit's `CommandRunner` calls
`capture_output=False` for this path so the prompt reaches the TTY.

## git commit signing

Inspect:

```bash
shimkit gpg git-signing show
shimkit gpg git-signing show --json
```

Configure:

```bash
shimkit gpg git-signing configure ABCD1234EF567890 --yes
shimkit gpg git-signing configure ABCD1234EF567890 --scope local --yes
shimkit gpg git-signing configure ABCD1234EF567890 --dry-run
```

`--scope global` (default) writes to `~/.gitconfig`. `--scope local`
writes to `.git/config` in the current repo only — useful when you
want different signing keys per project.

Each invocation writes two `git config` entries:

- `user.signingkey = <KEY_ID>`
- `commit.gpgsign = true`

Both go through `CommandRunner.run` (Rule 2 compliance — no
`subprocess` direct calls).

## Exporting public keys

```bash
shimkit gpg keys export ABCD1234EF567890                    # to stdout
shimkit gpg keys export ABCD1234EF567890 --dest pubkey.asc  # to file
```

Hand the `.asc` file to whoever needs to verify your signatures
(GitHub's "Add a GPG key" form, Keybase, etc.).

## JSON output

```bash
$ shimkit gpg keys list --json
{
  "ts": "...",
  "tool": "gpg",
  "step": "keys.list",
  "status": "ok",
  "data": {
    "keys": [
      {
        "key_id": "ABCD1234EF567890",
        "fingerprint": "ABCDEF1234567890ABCDEF1234567890ABCDEF12",
        "type": "ed25519",
        "bits": 256,
        "created": "2023-11-14",
        "expires": "2024-09-22",
        "expired": false,
        "uids": ["Real Name <name@example.com>"]
      }
    ]
  }
}
```

## Configuration

```json
{
  "tools": {
    "gpg": {
      "default_key_type": "ed25519",
      "default_key_expiry": "1y"
    }
  }
}
```

## Exit codes

| Code | Meaning                                                  |
|-----:|----------------------------------------------------------|
| 0    | success / no-op                                          |
| 1    | unknown key type / scope, gpg-exit non-zero, prompt cancel |
| 2    | Typer usage error                                        |
| 69   | EX_UNAVAILABLE — wrong platform, `gpg` (or `git` for git-signing) not on PATH |
| 130  | SIGINT                                                   |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | ✓ — `brew install gnupg`. |
| Linux    | ✓ — `apt install gnupg` or distro equivalent. |
| WSL      | ✓ (Linux path). |
| Windows  | ✗ — out of charter. |

## Security notes

- **Passphrases stay in gpg's TTY pinentry.** Never logged, never
  captured.
- **No private-key export.** `keys export` is public-only (`--armor
  --export`, not `--export-secret-keys`).
- **No automatic key trust changes.** Trust level adjustments
  (`--edit-key`) are deliberately out of scope; they're a per-user
  judgment call.
- **git-signing configure is the only mutator that touches git
  config.** It writes exactly two keys per invocation; no other
  config is modified.
