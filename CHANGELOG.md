# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `shimkit dns` — macOS DNS resolver recovery. Ports `fixdns.sh` with
  the BSD-grep, Wi-Fi-only, `timeout(1)`, and bash 3.2 spinner bugs
  fixed. Commands: `diagnose`, `flush`, `show`, `set`, `reset` (token),
  `test`, `profile list`, `fix` (6-step escalation with optional
  nuclear via `--confirm REGENERATE`), `rollback`,
  `diagnostics export`.
- `shimkit adguard` — AdGuard Home port-conflict fixer for Linux.
  Ports `fix-adguardhome-ports.sh` with the run-without-AGH, awk-yaml,
  NetworkManager-warning-only, and yaml-while-AGH-running bugs fixed.
  Prefers the HTTP control API; falls back to ruamel.yaml edits after
  stopping AGH. Commands: `scan`, `fix` (with `--dns-cleanup-only`,
  `--remap-only`, `--migrate-from-pihole`), `verify`, `ports
  show|set`, `config validate`, `service start|stop|restart|status`,
  `logs`, `rollback`.
- `shimkit docker-clean` — Docker resource cleanup for Linux + macOS +
  WSL. Ports `docker-nucker.sh` with the `local x=$(...); if [ $? -eq
  0 ]` always-success bug, `((var++))` set-e abort, and missing-named-
  buildx-builder bugs fixed. Uses the docker-py SDK; `docker desktop
  restart` for Docker Desktop 4.37+. Commands: `status`, `quick`,
  `nuke` (`--confirm DELETE`), `restart`, `stop-all`, `prune-images`,
  `prune-volumes`, `prune-networks`, `prune-builders`, `orphans`,
  `inspect`, `compose-down`, `schedule` (emit only — no install).
- Core: `shimkit.core.log` (stdlib logging with JSONL `--log-file`,
  with redaction of secret-looking keys), `shimkit.core.json_event`
  (typed `Event` for `--json` mode), `shimkit.core.systemd` (typed
  systemctl wrapper used by `adguard` and `docker-clean`),
  `shimkit.core.cli_flags` (shared Typer `Option` defaults used by
  every new subcommand for uniform `--dry-run`, `--json`, `--quiet`,
  `--verbose`, `--log-file`, `--timeout`, `--yes`).
- `UI.line` and `UI.set_quiet` — plain-output primitive plus a quiet
  mode that suppresses everything except `UI.error`.
- CI: new `security` job (bandit + pip-audit), `dockerfile-hadolint`,
  `build` (sdist+wheel artifact), `smoke` (install built wheel on
  macOS + Ubuntu and run the CLI). Pytest now runs with `--cov` and
  a **65%** coverage floor — **216 tests** total (the original 77
  plus 38 for the three new tools plus 101 follow-up tests targeting
  manager methods, fixer steps, pruner error paths, resolv mutators,
  api set_ports payload, desktop fallback, and the parsers in
  scutil/networksetup/client/yaml_editor/cgroup-v2). Per-tool
  coverage: dns 76% (scutil 96%, commands 93%), adguard 64%
  (yaml_editor 97%, finder 88%), docker_clean 73% (models 97%,
  schedule 86%). Raising toward 85% as additional tests land —
  remaining gaps are mostly in the interactive `run()` menus and
  the most destructive paths (nuclear plist reset, resolv mutators
  on real `/etc/*`), validated by Phase 7 manual smoke instead.
- CI: new `adguard-integration` job pinned to AGH v0.107.74. Downloads
  the upstream binary on ubuntu-latest, runs it on non-default ports
  (5300/8000) so it doesn't collide with the runner's
  systemd-resolved, pre-bakes a yaml with a bcrypt-hashed throwaway
  user, and exercises `shimkit adguard scan/verify/ports show/fix
  --dry-run/ports set --dry-run` against the live daemon. JSON output
  asserted; AGH log captured on failure. Closes the "v0.2.0 needs a
  real-Linux integration run" gap.
- ruff config: `extend-immutable-calls = ["typer.Argument",
  "typer.Option"]` so B008 stops false-positiving on Typer's API.

### Changed

- `cli.py` no longer calls `typer.echo` / `typer.secho` / `subprocess`
  directly. Every output path goes through `UI.*`; the `$EDITOR`
  launch in `config edit` goes through `CommandRunner.run(...,
  capture_output=False)`. `shimkit doctor` extended with `dns`,
  `adguard`, and `docker` probes.
- `shimkit adguard verify`, `adguard ports show`, `adguard ports set`,
  and `adguard config validate` now accept `--install PATH` (matching
  `adguard scan`/`adguard fix`). The flag overrides the auto-detected
  install path so non-root callers (CI, dev sandboxes) can point at
  an AGH instance outside the default candidate paths.
- `Brew.install_self` (Homebrew bootstrap) no longer interpolates the
  config-supplied URL into a shell command. URL is validated as HTTPS,
  downloaded to a tempfile, then executed via `/bin/bash <tmpfile>`.

### Security

- `bandit` and `pip-audit` are now CI gates. All `# nosec`
  suppressions have one-line justifications at the suppression site.
- `pkgmgr.PackageManager` templates now accept an argv-list form
  (preferred, no shell). `defaults.json` ships with argv lists for
  every PM. The legacy string-template form is kept for backward
  compatibility with existing user configs.
- `Brew.install_self` no longer interpolates a config URL into a
  shell command. It downloads to a tempfile (HTTPS scheme validated)
  and executes via `/bin/bash <tmpfile>` without shell.
- `dns.fixer._make_backup_dir` refuses paths outside `$HOME` or
  `/tmp`, so a malicious config can't redirect plist backups to
  `/etc`.
- `core.command` exports `is_root()` and `has_sudo_cached()`;
  `AdGuardManager.boot(require_root=True)` (used by `adguard fix`
  outside `--dry-run`) refuses to proceed without elevation.
- `Dockerfile` base image pinned by manifest digest
  (`python:3.12-slim@sha256:401f6e1a...`). Dependabot's `docker`
  ecosystem watches the line; new digests come in as reviewable PRs.

## [0.1.0] — Initial release

shimkit is a toolkit of developer utilities — Python tools, shimmed by
bash.

### Tools

- `shimkit java` — OpenJDK version manager: install / list / switch /
  upgrade / uninstall / remove-oracle. Supports macOS (Apple Silicon +
  Intel), Linux, WSL, and container environments. Interactive menu
  when called bare; scriptable subcommands otherwise.
- `shimkit shell` — Shell upgrader for bash / zsh / fish / ksh via
  whichever package manager the host provides (brew, apt, dnf, yum,
  pacman, apk, zypper). Warns before upgrading the currently active
  shell; `--force` to skip the prompt.
- `shimkit config` — Inspect, edit, and validate user configuration.
- `shimkit doctor` — System diagnostics (platform, shell, package
  manager, brew presence, config validity, install method).
- `shimkit self-update` — Detects how shimkit was installed
  (uv / pipx / brew / pip) and dispatches to the matching upgrade
  command. Queries PyPI for the latest version.

### Architecture

- Single `CommandRunner` chokepoint for every subprocess invocation.
- Cross-platform primitives in `shimkit.core`: Platform, Shell,
  ShellConfigWriter, PackageManager, UI (NO_COLOR-aware), Menu
  (questionary + stdin fallback).
- Layered JSON config with pydantic v2 schema, strict-mode key
  validation, auto-generated JSON Schema for editor autocomplete.
  Precedence: bundled defaults → `~/.config/shimkit/shimkit.json` →
  `$SHIMKIT_CONFIG` → `NO_COLOR`.
- Builder-pattern orchestrators: `Tool.create().boot().run()`.
- Fluent return-self contracts on UI, Shell, ShellConfigWriter.

### Distribution

- Installable via uv (`uv tool install shimkit`), pipx
  (`pipx install shimkit`), pip (`pip install --user shimkit`), or a
  Homebrew tap (`brew install simtabi/tap/shimkit`).
- One-liner installer hosted on GitHub Releases:

  ```bash
  curl -fsSL --proto '=https' --tlsv1.2 \
    https://github.com/simtabi/shimkit/releases/latest/download/install.sh \
    | sh
  ```

- PEP 561 `py.typed` marker — downstream consumers get full type
  hints. mypy strict + ruff + pytest run on CI for macOS + Ubuntu ×
  Python 3.10–3.13.

### Compatibility

- Python ≥ 3.10. macOS and Linux (including WSL, Docker, LXC,
  Kubernetes). Windows requires WSL.

[0.1.0]: https://github.com/simtabi/shimkit/releases/tag/v0.1.0

Copyright © 2026 [Simtabi LLC](https://simtabi.com). MIT licensed.
