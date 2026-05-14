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
  a **65%** coverage floor — **233 tests** at HEAD (the original 77
  plus 38 for the three new tools plus 101 follow-up tests targeting
  manager methods, fixer steps, pruner error paths, resolv mutators,
  api set_ports payload, desktop fallback, and the parsers in
  scutil/networksetup/client/yaml_editor/cgroup-v2, plus 11 from the
  cleanup-2026-05-14 pass covering CLI-flag wiring, MODERATE prompts,
  extras-missing exit 69, and EX_CONFIG exit 78). Per-tool
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

### Removed

- The `installer/` directory (`install.sh` and the Homebrew formula
  template). The custom `curl | sh` installer is no longer
  shipped — installation goes through the direct package-manager
  channels (`uv tool install shimkit` / `pipx install shimkit` /
  `pip install --user shimkit` / `brew install simtabi/tap/shimkit`).
  Side effects:
  - `installer-shellcheck` CI job removed.
  - `release.yml`'s install.sh + install.sh.sha256 asset upload
    steps removed; SBOM is still uploaded to the GitHub Release.
  - `self_update.install_one_liner()` renamed to `install_commands()`
    and now returns the list of direct install commands rather
    than the curl-pipe URL.
  - README, `docs/installation.md`, `docs/release.md`,
    `docs/release-notes/v0.2.0.md`, `docs/validation-scope.md`,
    `prompt.md`, `SECURITY.md`, and the PR template scrubbed of
    install.sh references.

### Added (post the initial Unreleased section, in commit order)

- `scripts/test_adguard_mutating.sh` and the
  `adguard-mutating-integration` CI job: run the real
  `shimkit adguard fix` (and `ports set` yaml fallback) inside a
  privileged systemd container with `systemd-resolved` AND
  NetworkManager active. Asserts the drop-in path, the
  resolv.conf rewrite, the NM `dns=none` drop-in, and the
  AGH-stop-edit-start dance. Covers six of the seven Phase 7
  manual items; only the real-link-event check remains manual.
- `docs/plans/known-issues.md`: documents the one Phase 7 check
  that cannot be automated (real NetworkManager link-event
  survival on a real desktop), why containers can't validate it,
  and the manual procedure for release-time verification.
- `docs/plans/cleanup-2026-05-14.md`: end-of-session audit of
  gaps between shipped docs and shipped code (notably:
  partially-wired CLI flags, missing MODERATE-tier prompts, test
  coverage of CLI plumbing). Cleanup plan included.
- Shared CLI flags now wired through every new tool's Typer
  callback: `--quiet`, `--verbose`, `--log-file`, `--no-color`,
  `--color {auto,always,never}`, `--no-input`. Previously declared
  in `core/cli_flags.py` but only some commands consumed them;
  the rest silently dropped the flag.
- `Menu.prompt_for_change()` and `UI.set_no_input()` /
  `UI.set_color_mode()` so MODERATE-tier confirmations can be
  short-circuited by `--yes` / `--force` and skipped under
  `--no-input` (returns refusal rather than blocking).
  `shimkit dns set`, `shimkit adguard ports set`, and the
  `shimkit docker-clean prune-*` family now use this — the brief
  promised MODERATE prompts but no command implemented them.
- Test coverage: `--quiet`, `--verbose`, `--log-file`,
  `--no-color`, `--color`, `--no-input` exercised at the
  app-callback level; MODERATE-tier prompt exercised on
  `shimkit dns set`; extras-missing → exit 69 exercised on both
  `adguard` and `docker-clean` (sabotaging `psutil` and `docker`
  imports). Closes the brief's "mandatory minimum" gap.
- `tests/conftest.py` autouse fixture resets `UI._quiet` /
  `_color_override` / `_no_input` and the log file-handler state
  between tests so a flag-setting test doesn't bleed into the
  next.

### Fixed (post the initial Unreleased section)

- `Systemd.write_drop_in` accepts an optional `target_dir=` kwarg;
  `adguard.disable_resolved_stub()` now writes to
  `/etc/systemd/resolved.conf.d/` (the `[Resolve]` config dir),
  not `/etc/systemd/systemd-resolved.service.d/` (service-unit
  override dir, which systemd-resolved silently ignores for
  `[Resolve]`-section directives). **This bug silently disabled
  the entire "disable stub listener" feature on every real run
  prior to v0.2.0** — the drop-in landed in the wrong directory
  and systemd-resolved kept holding port 53.
- `adguard.write_resolv_symlink()`, `write_resolv_static()`,
  `configure_network_manager()` now return `bool` indicating
  whether the operation actually succeeded. `manager.fix()`
  aggregates these honestly: `outcome.applied = True` only when
  every sub-step succeeded; `outcome.error` is set on failure.
  Previously the orchestrator unconditionally claimed success
  even when sub-steps silently failed.
- `manager.fix()` notes now reflect what actually happened per
  step. Previously the "NetworkManager dns=none drop-in written"
  note was emitted regardless of whether NM was active —
  misleading users on headless servers without NM installed.
- `write_resolv_static()` falls back to a Python direct-write
  through the existing inode when `sudo install` fails. Handles
  the Docker bind-mounted `/etc/resolv.conf` case without
  breaking the atomic-replace path on real hosts.
- `adguard yaml_editor.read_ports()` now reads `http.address`
  ("host:port") as the canonical AGH 0.107.x form for the web UI
  port; falls back to legacy `http.port`. `set_ports()` writes
  `http.address` and updates `http.port` if present in the file
  for consistency. AGH's schema-version-34 migration drops
  `http.port` and keeps `http.address`; the previous read path
  reported the wrong port after AGH's first config rewrite.
- `cli.py::doctor()` docker probe shells out to `docker version
  --format '{{.Server.Version}}'` via `CommandRunner` instead of
  going through the docker-py SDK. Avoids a lingering Unix-socket
  fd that triggered pytest's UnraisableException warning on
  Python 3.12+ and failed the next-running test.
- `cli.py::config edit` no longer imports `subprocess` directly;
  the `$EDITOR` launch goes through `CommandRunner.run(...,
  capture_output=False)` (Rule 2 compliance).
- `tools/adguard/ports._pid_to_unit()` accepts an injectable
  `proc_root=` parameter; the test no longer subclasses `Path`
  (which broke on Python 3.12+ when pathlib internals changed
  `_parts` → `_raw_paths`).
- `shimkit adguard rollback` now accepts `--install PATH` for
  consistency with the other `adguard` subcommands.
- `mypy strict` no longer false-positives on optional-extra
  modules (`ruamel.yaml`, `requests`, `psutil`, `docker`,
  `dnspython`) via `[[tool.mypy.overrides]]` in `pyproject.toml`.
  CI installs `[dev]` only by default; without the override,
  every type-check matrix cell failed with `import-not-found`.
- `pip-audit` in CI now runs without `--strict`. The combination
  of `--strict` and `--skip-editable` was a footgun: the latter
  was meant to silently skip the editable shimkit install, but
  the former promoted the skip notice to a hard error.
- `hadolint` in CI now ignores `DL3013` (pin pip versions) in
  addition to `DL3008`. We deliberately want the latest pip in
  the build stage.
- `[dev]` extras now include `ruamel.yaml`, `requests`, `psutil`,
  `docker`, and `dnspython` so the test matrix doesn't fail with
  `ModuleNotFoundError` when running the new tool tests.
- `adguard-integration` CI job's wait-loop curl now passes Basic
  auth (`ADGUARD_USER` / `ADGUARD_PASS`). With `users:` populated
  in the pre-baked yaml, AGH gates `/control/status` behind
  auth — an unauthenticated curl gets 401 and `-f` makes the loop
  time out even when AGH is healthy.
- `UI._color_enabled()` is resilient to a broken config: previous
  code called `get_config().ui.color`, which re-raised
  `ConfigError` when validation failed — the very `UI.error()`
  call meant to explain the problem then crashed with a secondary
  exception, leaving the user with a Python traceback instead of
  the config error. UI now falls back to TTY auto-detect when
  `get_config()` fails.
- `shimkit config validate` now exits **78** (EX_CONFIG, from
  `sysexits.h`) on validation failure, distinct from generic exit
  1. Scripts can detect "config is broken" specifically. Previously
  documented in the brief but never wired.

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
