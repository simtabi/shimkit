# shimkit — current architecture (as of v0.4.0 / `89014ee`)

This is the **target** for the ubuntu/ migration. Captures the
patterns to honor rather than the patterns to invent. See
[`architecture-target.md`](./architecture-target.md) for what's
proposed *after* the migration.

## High-level shape

```
src/shimkit/
├── __init__.py            __version__
├── cli.py                 Top-level Typer dispatcher; registers every tool subapp
├── self_update.py         shimkit's own update path (uv / pipx / brew / pip detect)
├── core/                  Cross-cutting primitives (Rule chokepoints live here)
│   ├── command.py         CommandRunner — Rule 2 (every subprocess goes through here)
│   ├── ui.py              UI — Rule 5 (every stdout write goes through here)
│   ├── menu.py            Menu — prompt_for_change (MODERATE), select / confirm
│   ├── pkgmgr.py          PackageManager — argv templates, no shell=True
│   ├── platform.py        Platform.detect()
│   ├── shell.py           Shell detection
│   ├── systemd.py         Systemd — wrapper for systemctl / drop-ins
│   ├── log.py             Logger with secret-key redaction
│   ├── json_event.py      Event dataclass for `--json` emission
│   └── cli_flags.py       Shared Typer Option singletons (QUIET, VERBOSE, …)
├── config/                pydantic-settings schema + JSON defaults
│   ├── defaults.json      Bundled baseline (every tool's config)
│   ├── schema.py          Strict pydantic models (extra=forbid)
│   ├── loader.py          Layered: defaults → ~/.config/shimkit/shimkit.json → $SHIMKIT_CONFIG
│   └── errors.py          ConfigError → exit 78 (EX_CONFIG)
└── tools/                 One package per `shimkit <tool>` subapp
    ├── java/              Original tools
    ├── shell/
    ├── dns/               Per-charter ("host-machine dev-workflow"):
    ├── adguard/             — these read+optionally mutate per-user state
    ├── docker_clean/        on the *existing* machine.
    ├── ports/             More:
    ├── hosts/
    ├── ssh/
    ├── env/
    ├── gpg/
    └── logs/
```

11 tools shipped. Every one follows the same shape:

```
tools/<name>/
├── __init__.py            Re-exports Manager + key models
├── commands.py            Typer subapp; thin dispatcher; MODERATE/SEVERE gates
├── manager.py             Orchestrator — owns CommandRunner shell-outs
├── models.py              Frozen dataclasses
└── <feature>.py           Pure parsers / scanners / editors (no I/O)
```

## Five load-bearing rules (from `CONTRIBUTING.md`)

1. **Every subprocess goes through `CommandRunner.run(argv_list)`.**
   No `subprocess.run` direct calls. No `shell=True`. argv is a list.
2. **Every output goes through `UI.*`.** No `print`, no `typer.echo`.
   `UI.line` / `UI.success` / `UI.info` / `UI.warning` / `UI.error` /
   `UI.dim` / `UI.header`. `emit_json(Event)` for `--json` mode.
3. **Config-driven values live in `defaults.json`.** Anything a user
   might want to tune ends up in the typed pydantic schema. No magic
   strings in code.
4. **Builder pattern: `Manager.create().boot().run()`.** Two-stage
   construction so `boot()` can fail fast with exit 69 on platform /
   missing-binary checks before any work happens.
5. **Fluent self returns from builder methods.**

## Public CLI surface (v0.4.0)

```
shimkit                       Top-level help
shimkit doctor                System diagnostics
shimkit self-update           Update shimkit itself
shimkit version
shimkit config show / path / edit / validate
shimkit java …                Original tools
shimkit shell …
shimkit dns …                 macOS DNS recovery
shimkit adguard …             AGH port-conflict fixer (Linux)
shimkit docker-clean …
shimkit ports …               Cross-platform port owner + killer
shimkit hosts …               /etc/hosts editor with atomic write + backup
shimkit ssh keys / agent / known-hosts / perms / config
shimkit env …                 .env viewer + scaffolder
shimkit gpg keys / agent / git-signing
shimkit logs tail / grep / system show
```

Universal flags (always before the subcommand):
`--quiet -q`, `--verbose -v`, `--log-file PATH`, `--no-color`,
`--color {auto,always,never}`, `--no-input`.

Per-command flags (after the subcommand):
`--json`, `--dry-run -n`, `--yes -y`, `--force -f`, `--confirm TOKEN`.

## Confirmation tiers

| Tier | Trigger | How to skip |
|------|---------|-------------|
| **NONE** | Read-only, idempotent reads | n/a |
| **MODERATE** | Mutators that affect per-user state | `--yes`, `--force`, or interactive `[y/N]`. Under `--no-input` or non-TTY: refuse with exit 1. |
| **SEVERE** | Destructive / system-wide / irreversible | Per-tool token from config: `--confirm KILL-INIT`, `--confirm DELETE`, `--confirm APPLY-LIST`. |

`prompt_for_change(description, yes, force, no_input)` is the
single chokepoint in `core/menu.py`.

## JSON configurator (the design pattern to extend)

`config/defaults.json` is the bundled baseline. Users override at
`~/.config/shimkit/shimkit.json` (or `$SHIMKIT_CONFIG`). `loader.py`
merges defaults → user-override → env, validates via the strict
pydantic schema, and surfaces `ConfigError` with field-pointing
errors on failure. `shimkit config validate` exits 78 on failure.

Schema rules:

- `_StrictModel` (`extra="forbid"`) — unknown keys are an error,
  not silently accepted. Catches typos in user configs.
- `$schema` meta-key is stripped before validation (so IDE JSON-
  schema integration works).
- One model per tool: `JavaConfig`, `DnsConfig`, `EnvConfig`, etc.
  All hang off `ToolsConfig` under `ShimkitConfig.tools`.
- Defaults live in the model field defaults; `defaults.json` mirrors
  them for IDE discoverability.

## Error model

| Exit | Meaning | When |
|-----:|---------|------|
| 0    | success / no-op | normal |
| 1    | generic failure | most failures |
| 2    | usage error | Typer's automatic for bad CLI args |
| 64   | EX_USAGE | reserved |
| 69   | EX_UNAVAILABLE | wrong platform, missing binary, missing optional extra |
| 77   | EX_NOPERM | needs root / sudo / docker group |
| 78   | EX_CONFIG | invalid shimkit config |
| 130  | SIGINT | Ctrl-C |

Exit code is the contract between shimkit and any script wrapping it.

## Logging

`core/log.py` exposes `get_logger("toolname")`. Each tool gets a
namespaced logger under `shimkit.<tool>`. `attach_file_handler(path)`
adds a JSONL `FileHandler` whose formatter:

- Writes one JSON object per line
- UTC ISO-8601 timestamp
- Recursively redacts dict keys matching
  `password|passwd|pwd|secret|token|api[_-]?key|authorization`
  (case-insensitive)

`shimkit env` reuses the same key-matcher shape for `.env`
redaction — single source of truth for "what counts as a secret name".

## Test layout

```
tests/
├── conftest.py            Autouse fixtures (UI/log reset, env cleanup, runner)
├── test_cli.py            Top-level CLI integration
├── test_config.py         Schema + loader + EX_CONFIG
├── test_pkgmgr.py
├── test_self_update.py
├── test_tools_<name>.py   One per tool — 14–60 tests each
└── …
```

Mocks at `CommandRunner.run`, `Platform.detect`, and pure-parser
fixtures. **Never touches real `/etc/*`, real `~/.ssh`, or the
network** — every system boundary is faked.

Coverage floor enforced at 65% via `--cov-fail-under` in `pyproject`.

## CI / Release

`.github/workflows/ci.yml`:

- `test` — 8 matrix cells (macOS + Ubuntu × Python 3.10/3.11/3.12/3.13)
- `security` — bandit `-ll` (fail on medium+) + pip-audit
- `build` — sdist + wheel
- `smoke` — install built wheel into a fresh venv + run CLI
- `adguard-integration` — real AGH v0.107.74 on ubuntu-latest
- `adguard-mutating-integration` — privileged systemd container

`.github/workflows/release.yml` triggers on `v*` tags:
`guard → build → github-release`. PyPI publishing + GHCR were
removed in v0.2.3 (PyPI deferred per `shipping-checklist.md`
Phase 4; container was a testing artifact, not a release channel).

## Patterns the migration must honor

- Tool naming: lowercase, single word, no underscores in the subcommand
  (`docker-clean` is `docker_clean` in the Python package, hyphenated
  at the Typer level via `name="docker-clean"`).
- Every public method gets a docstring with at least one usage example.
- No global state. Configuration flows via `get_config()`.
- `--dry-run` makes zero `CommandRunner.run` calls (asserted in tests
  via monkeypatch).
- MODERATE prompt: `Menu.prompt_for_change(description, yes=, force=,
  no_input=UI.is_no_input())`.
- New optional dependency? Add an extras entry in `pyproject.toml`
  (`docker-clean = ["docker>=7.1"]`) and boot-time-detect it with
  exit 69 + "install command" hint.

## Patterns the migration must NOT introduce

- `subprocess.run` direct calls (Rule 2 violation).
- `print` / `typer.echo` (Rule 5 violation).
- Hidden global state.
- Magic strings instead of config.
- Breaking changes to public API without a deprecation cycle.
- Network calls in tests (CI runs offline by default).
- Hard-coded user-specific paths (`/home/vagrant`, `/home/<user>`).

## Extension pattern

Adding a new tool today:

1. `src/shimkit/tools/<name>/{__init__,commands,manager,models}.py`
2. `config/defaults.json` + `config/schema.py` add `<Name>Config`
   under `ToolsConfig`.
3. `cli.py` imports `<name>_app` and registers via `app.add_typer`.
4. `tests/test_tools_<name>.py` with ≥ the mandatory-minimum tests
   (boot smoke, EX_UNAVAILABLE on wrong platform, every subcommand
   happy + sad, `--json` parses, `--dry-run` is a no-op, MODERATE
   refusal under `--no-input`).
5. `docs/tools/<name>.md` from the existing template.
6. README's tool list + CHANGELOG `[Unreleased]` `### Added` entry.

The pattern is mechanical enough that the migration plan should be
"one feature → one tool package → one PR" rather than a single
mega-PR.
