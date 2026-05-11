# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
