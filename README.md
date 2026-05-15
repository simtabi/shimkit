# shimkit

A toolkit of developer utilities. Python tools, shimmed by bash.

```
$ shimkit --help
shimkit
  java          Manage OpenJDK installations.
  shell         Manage shell installations and upgrades.
  config        Inspect and edit shimkit configuration.
  doctor        Print system diagnostics useful for bug reports.
  self-update   Update shimkit itself to the latest release.
  version       Print the shimkit version.
```

## Install

```bash
uv tool install shimkit
pipx install shimkit
brew install simtabi/tap/shimkit
pip install --user shimkit
```

Full install matrix, optional dependency extras, and self-update
behaviour: [`docs/installation.md`](docs/installation.md).

## Tools

- **[`shimkit java`](docs/tools/java.md)** — OpenJDK version manager.
  Install / list / switch / upgrade / uninstall / remove-oracle on macOS
  and Linux (incl. WSL, Docker).
- **[`shimkit shell`](docs/tools/shell.md)** — Upgrade `bash` / `zsh` /
  `fish` / `ksh` via brew, apt, dnf, yum, pacman, apk, or zypper.
- **[`shimkit dns`](docs/tools/dns.md)** — macOS DNS resolver recovery.
  Diagnose, flush, fix (6-step escalation), test, rollback, and dump
  diagnostic bundles.
- **[`shimkit adguard`](docs/tools/adguard.md)** — AdGuard Home
  port-conflict fixer (Linux). API-first, yaml fallback, with
  systemd-resolved / NetworkManager handling.
- **[`shimkit docker-clean`](docs/tools/docker-clean.md)** — Docker
  resource cleanup (Linux + macOS + WSL). Status, quick, prune-*, nuke,
  schedule-snippet emit.
- **[`shimkit ports`](docs/tools/ports.md)** — list / kill the process
  holding a TCP or UDP port (macOS + Linux). `lsof` on macOS, `ss` on
  Linux. MODERATE prompt on `kill`; severe token for system-tier PIDs.
- **[`shimkit hosts`](docs/tools/hosts.md)** — `/etc/hosts` editor
  with atomic-write + timestamped backups. add / remove / block /
  unblock / apply-list (severe) / rollback. macOS + Linux.
- **[`shimkit ssh`](docs/tools/ssh.md)** — SSH key + agent +
  known_hosts + perms hygiene. keys list/generate/rotate, agent
  status/add, known-hosts audit/prune, perms audit/fix, config
  show. No third-party deps; passphrases handled by ssh-keygen.
- **[`shimkit env`](docs/tools/env.md)** — `.env` viewer +
  scaffolder with default-deny secret redaction. show / list /
  scaffold / diff / redact. macOS + Linux.
- **[`shimkit gpg`](docs/tools/gpg.md)** — GPG key + git-signing
  hygiene. keys list/generate/export, agent status, git-signing
  show/configure. No third-party deps; passphrases handled by gpg.

Plus three utilities:

- `shimkit config` — inspect, edit, validate user configuration
  ([details](docs/configuration.md))
- `shimkit doctor` — system diagnostics for bug reports
- `shimkit self-update` — keep shimkit current
  ([details](docs/installation.md#updates))

## Documentation

The repo root has the short version. The long version lives under
[`docs/`](docs/):

| Topic | Doc |
|-------|-----|
| Install methods, the one-liner, updates, uninstall | [`docs/installation.md`](docs/installation.md) |
| Config layer, schema, examples | [`docs/configuration.md`](docs/configuration.md) |
| Architecture, the load-bearing rules, how to add a new tool | [`docs/architecture.md`](docs/architecture.md) |
| Cutting a release, what each CI job does | [`docs/release.md`](docs/release.md) |
| Shipping checklist (what's done vs what's pending) | [`docs/shipping-checklist.md`](docs/shipping-checklist.md) |
| `shimkit java` deep-dive | [`docs/tools/java.md`](docs/tools/java.md) |
| `shimkit shell` deep-dive | [`docs/tools/shell.md`](docs/tools/shell.md) |

Project files:

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — coding conventions, test
  patterns, PR expectations
- [`SECURITY.md`](SECURITY.md) — vulnerability disclosure
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — Contributor Covenant 2.1
- [`CHANGELOG.md`](CHANGELOG.md) — release history

## Development

```bash
git clone https://github.com/simtabi/shimkit
cd shimkit
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check src tests
mypy src/shimkit
```

CI runs the same four commands on macOS + Ubuntu × Python 3.10/3.11/3.12/3.13.

## License

MIT — see [`LICENSE`](LICENSE).
