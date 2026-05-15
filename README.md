# shimkit

A toolkit of developer utilities. Python tools, shimmed by bash.

```
$ shimkit --help
shimkit
  java          Manage OpenJDK installations.
  shell         Manage shell installations and upgrades.
  dns           macOS DNS resolver recovery.
  adguard       AdGuard Home port-conflict fixer (Linux).
  docker-clean  Docker resource cleanup.
  ports         Inspect / kill the process holding a TCP/UDP port.
  hosts         /etc/hosts editor with atomic-write + backups.
  ssh           SSH key + agent + known_hosts + perms hygiene.
  env           .env viewer + scaffolder with secret redaction.
  gpg           GPG key + git-signing hygiene.
  logs          System log tail / grep.
  db            Container-first databases (5 engines).
  stack         Multi-container app recipes (LEMP today).
  web           Web-server tooling (nginx vhost generator).
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
- **[`shimkit logs`](docs/tools/logs.md)** — system log tail / grep.
  macOS `log show/stream`, Linux `journalctl`. Read-only — no
  mutators, no prompts.

### Server-class tools (Docker-first; opt-in to host install)

- **[`shimkit db`](docs/tools/db.md)** — container-first databases
  (mysql / mariadb / postgres / mongo / phpmyadmin). `up` / `down`
  / `shell` / `dump` / `reset` (SEVERE) / `status` / `ls`. No
  host-install path; the container is the source of truth.
- **[`shimkit web nginx vhost`](docs/tools/web.md)** — hardened
  nginx vhost generator. File-only by default; `apply` and
  `remove` are SEVERE-tier. Three flavors: static / php / laravel.
- **[`shimkit stack lemp`](docs/tools/stack.md)** — three-container
  LEMP recipe (db + php-fpm + nginx). Bind-mounts `$cwd` at
  `/srv/app`. `up` / `down` / `status` / `logs` / `exec`. Multiple
  projects side-by-side via `--project`.
- `shimkit shell colors` — 256-color ANSI palette diagnostic.

Plus three utilities:

- `shimkit config` — inspect, edit, validate user configuration
  ([details](docs/configuration.md))
- `shimkit doctor` — system diagnostics for bug reports
- `shimkit self-update` — keep shimkit current
  ([details](docs/installation.md#updates))

## Version requirements

shimkit declares minimum versions for the external binaries it
shells out to (docker / nginx / git / gpg / python). The registry
lives under `tools.versions` in the JSON config and is consulted at
three points:

1. Each tool's `boot()` runs a preflight; out-of-range / missing
   tools exit 69 with a platform-specific install hint.
2. `shimkit doctor` prints the full versions table.
3. The same registry is rendered into the install docs.

Override per-install in `~/.config/shimkit/shimkit.json`. Full
spec: [`.design/version-constraints-spec.md`](.design/version-constraints-spec.md).

## Architecture

Quick overview at [`docs/architecture.md`](docs/architecture.md).
Deep reference under [`.design/`](.design/):

- [`.design/architecture-current.md`](.design/architecture-current.md)
  — pre-migration snapshot (the five load-bearing rules, JSON
  configurator, MODERATE/SEVERE prompt model, EX_* exit codes).
- [`.design/architecture-target.md`](.design/architecture-target.md)
  — post-migration layout (adds `core/docker.py`, `core/version.py`,
  and the `db` / `stack` / `web` sub-trees).
- [`.design/version-constraints-spec.md`](.design/version-constraints-spec.md)
  — the constraints subsystem in detail.
- [`.design/plans/migration-plan.md`](.design/plans/migration-plan.md)
  — the v0.5.0 work-item plan; useful for understanding why a
  given module exists.

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
| `shimkit dns` deep-dive | [`docs/tools/dns.md`](docs/tools/dns.md) |
| `shimkit adguard` deep-dive | [`docs/tools/adguard.md`](docs/tools/adguard.md) |
| `shimkit docker-clean` deep-dive | [`docs/tools/docker-clean.md`](docs/tools/docker-clean.md) |
| `shimkit ports` deep-dive | [`docs/tools/ports.md`](docs/tools/ports.md) |
| `shimkit hosts` deep-dive | [`docs/tools/hosts.md`](docs/tools/hosts.md) |
| `shimkit ssh` deep-dive | [`docs/tools/ssh.md`](docs/tools/ssh.md) |
| `shimkit env` deep-dive | [`docs/tools/env.md`](docs/tools/env.md) |
| `shimkit gpg` deep-dive | [`docs/tools/gpg.md`](docs/tools/gpg.md) |
| `shimkit logs` deep-dive | [`docs/tools/logs.md`](docs/tools/logs.md) |
| `shimkit db` deep-dive | [`docs/tools/db.md`](docs/tools/db.md) |
| `shimkit stack` deep-dive | [`docs/tools/stack.md`](docs/tools/stack.md) |
| `shimkit web nginx` deep-dive | [`docs/tools/web.md`](docs/tools/web.md) |

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
