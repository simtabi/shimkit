# Architecture

shimkit is a collection of developer tools that share a small set of
primitives. Every tool is built the same way: orchestrator class,
non-interactive methods, optional menu loop, Typer commands.

> **Deep reference.** This page is the quick tour. The
> [`.design/`](../.design/) directory has the full architecture
> documents:
>
> - [`architecture-current.md`](../.design/architecture-current.md) —
>   pre-v0.5.0 snapshot.
> - [`architecture-target.md`](../.design/architecture-target.md) —
>   v0.5.0 layout with the new `db` / `stack` / `web` sub-trees and
>   two new core primitives (`core/version`, `core/docker`). v0.6+
>   additions (cron, framework, tls, host_service) follow the same
>   patterns and slot into the same tree.
> - [`version-constraints-spec.md`](../.design/version-constraints-spec.md) —
>   how tool-version checks work.

## Layout

```
src/shimkit/
  cli.py              Top-level Typer dispatcher
  self_update.py      shimkit-itself upgrade flow
  config/             Layered JSON config + pydantic schema
    schema.py         pydantic models (the schema source of truth)
    defaults.json     Bundled defaults (the values source of truth)
    loader.py         Layered load + deep-merge + env overrides
    errors.py         ConfigError
  core/               Shared primitives — every tool depends on these
    command.py        CommandResult, CommandRunner, sudo_prefix,
                      is_root, has_sudo_cached
    platform.py       Platform — OS/arch/WSL/container detection
    shell.py          Shell, ShellConfigWriter, java_home_for
    pkgmgr.py         PackageManager (brew/apt/dnf/yum/pacman/apk/zypper).
                      Accepts argv-list templates (preferred, no shell)
                      and legacy string templates (back-compat)
    ui.py             Colour-aware terminal output + boxed banner.
                      UI.line() for plain output, UI.set_quiet() for
                      the shared --quiet flag
    menu.py           questionary wrapper with stdin fallback
    log.py            Stdlib logging adapter; JSONL FileHandler with
                      secret-key redaction (opt-in via --log-file)
    json_event.py     Typed Event for --json output mode
    systemd.py        Linux systemctl wrapper; drop-in writer
    cli_flags.py      Shared Typer Option defaults so every tool's
                      subcommands have identical --dry-run/--json/
                      --quiet/--verbose/--log-file/--timeout semantics
    docker.py         DockerEnv — single chokepoint for the docker-py
                      SDK. Standardises container naming
                      (shimkit-<scope>-<kind>-<id>) + volume layout.
                      Refuses deletion outside ~/.shimkit/data/.
                      Added in v0.5.0; gained run_oneshot() in v0.8.0.
    host_service.py   HostService — cross-platform service-manager
                      facade. SystemdHost (Linux) + BrewServicesHost
                      (macOS). Added in v0.9.0 for `shimkit db
                      --on-host`; available to any future tool that
                      manages host daemons.
    version.py        Tool-version detection + constraint enforcement.
                      One source of truth (tools.versions registry)
                      consulted at three points: install docs, runtime
                      preflight, `shimkit doctor`. Eight built-in
                      detectors: docker, nginx, git, gpg, python,
                      php (v0.7), openssl (v0.8).
  tools/
    java/             OpenJDK manager (macOS + Linux)
    shell/            Shell upgrader (bash/zsh/fish/ksh) + colors
    dns/              macOS DNS resolver recovery (port of fixdns.sh)
    adguard/          AdGuard Home port-conflict fixer (Linux)
    docker_clean/     Docker resource cleanup (Linux + macOS + WSL)
    ports/            TCP/UDP port owner lookup + kill (v0.3.0)
    hosts/            /etc/hosts editor with atomic write (v0.3.0)
    ssh/              SSH keys + agent + perms hygiene (v0.3.0)
    env/              .env viewer + scaffolder, secret redaction (v0.4.0)
    gpg/              GPG keys + git-signing config (v0.4.0)
    logs/             System log tail/grep (macOS + Linux) (v0.4.0)
    db/               Container-first databases (6 engines) (v0.5.0)
                      + --on-host mode (v0.9.0) + redis engine (v0.15.0)
    stack/            Multi-container app recipes (LEMP today) (v0.5.0)
    web/nginx/        Hardened nginx vhost generator (v0.5.0)
    cron/             Generic user-crontab editor (v0.6.0)
    tls/              TLS cert lifecycle via certbot container (v0.8.0)
                      + dns-cloudflare (v0.13.0) + dns-route53 (v0.17.0)
    framework/        Framework recipes: laravel (v0.7.0),
                      symfony (v0.14.0), django (v0.16.0)
```

## The five load-bearing rules

These come straight from [CONTRIBUTING.md](../CONTRIBUTING.md#architecture-rules)
— restated here for the documentation context.

1. **Every tool builds on `shimkit.core` primitives.** No tool
   re-implements subprocess execution, OS detection, package-manager
   dispatch, shell detection, rc-file writing, terminal output, or
   interactive prompts.
2. **`CommandRunner` is the only place that calls `subprocess`.**
   Single audit chokepoint. Tests mock at this layer. The
   `subprocess` import does not appear anywhere else under
   `src/shimkit/`.
3. **Config values come from `shimkit.config.get_config()`.**
   Class-level constants for user-facing data belong in the schema +
   defaults.json. Logic-critical strings (idempotency markers, regex
   patterns) stay in code.
4. **Builder pattern for orchestrators.** Every tool's top-level
   class follows `Tool.create().boot().run()`. `run()` is the
   interactive menu; non-interactive subcommands call methods like
   `install(version)`, `list_things()`.
5. **Fluent contracts return `self`.** Chainable APIs where idiomatic
   (Shell, ShellConfigWriter, UI).

### Two cross-cutting patterns added with the new tools

Not new rules — patterns that emerged from porting the three shell
scripts and are now load-bearing for any future tool that touches
the same surfaces.

- **Argv-list package-manager templates.** `PackageManager` accepts
  command templates as either strings (legacy, rendered with
  `shell=True`) or argv lists (preferred, rendered with
  `shell=False`). New tools and new `defaults.json` rows use the
  argv form so a malicious or fat-fingered package name cannot
  inject shell metacharacters. See
  [`src/shimkit/core/pkgmgr.py`](../src/shimkit/core/pkgmgr.py).
- **Severe-tier confirmation tokens.** Destructive subcommands
  refuse to proceed without `--confirm <token>`, where the token
  comes from config. `--yes` alone does not bypass. Example:
  `shimkit docker-clean nuke --confirm DELETE`. The token is
  configurable per-environment.

## Per-tool structure

Each tool is a subpackage under `tools/`:

```
tools/<name>/
  __init__.py          Re-exports the tool's public API
  models.py            Value objects (dataclasses)
  manager.py           Top-level orchestrator (builder pattern)
  commands.py          Typer subcommand surface for the tool
  <component>.py       One or more domain modules
```

`shimkit/tools/java/` for reference:

```
java/
  __init__.py          JavaManager, JavaScanner, ...
  models.py            JavaVersion, JavaInstallation (dataclasses)
  brew.py              Brew (Homebrew operations)
  scanner.py           JavaScanner (multi-source discovery)
  oracle.py            OracleRemover (macOS Oracle cleanup)
  installer.py         JavaInstaller (install/uninstall/upgrade/switch)
  manager.py           JavaManager (orchestrator + interactive menu)
  commands.py          shimkit java {install,list,switch,...}
```

## How `shimkit` runs

```
shimkit java install 21
       │
       ▼
src/shimkit/cli.py: app
       │
       ▼ app.add_typer(java_app)
src/shimkit/tools/java/commands.py: install()
       │
       ▼
JavaManager.create().boot().install("21")
       │
       ▼
boot() wires:
       ┌─────────────────────────────────────────────────┐
       │  Platform.detect()                              │
       │  Shell.detect(platform).ensure_config_exists()  │
       │  Brew(platform)                                 │
       │  JavaScanner(platform, brew)                    │
       │  JavaInstaller(platform, brew, shell)           │
       │  OracleRemover(platform)                        │
       └─────────────────────────────────────────────────┘
       │
       ▼ install()
JavaInstaller.install("21")
       │
       ▼
brew.install_pkg("openjdk@21") + symlink + write env exports
       │
       ▼
ShellConfigWriter.for_shell(shell).write_java_env(prefix, "21", platform)
       │
       ▼  (idempotent — marker comment in rc file)
~/.zshrc gets a "# java-manager:openjdk@21" block with PATH + JAVA_HOME
```

## Bare invocation drops into the menu

`shimkit java` with no subcommand calls `JavaManager.create().boot().run()`
— the interactive menu loop. The menu's `_menu_*` methods call the
same non-interactive methods that the Typer subcommands call. Single
source of truth per operation.

```
shimkit java                    →  interactive menu
shimkit java install 21         →  direct install
shimkit java install            →  install config.tools.java.default_version
```

## Config flow

```
shimkit.config.get_config()
       │
       ▼  @functools.lru_cache(maxsize=1)
loader.load()
       │
       ▼
bundled_defaults_path() ─► json.load
       │
       ▼  deep_merge
user_config_path() ─► json.load   (if exists)
       │
       ▼  env overrides (NO_COLOR)
       │
       ▼  ShimkitConfig.model_validate(...)
ShimkitConfig instance (frozen pydantic v2)
```

`reset_cache()` clears the lru_cache. Tests use it between cases.

## Adding a new tool

1. Create `src/shimkit/tools/<name>/` with the standard layout above.
2. Add a config section to `schema.py` (pydantic model) and
   `defaults.json` (values). Regenerate `config/shimkit.schema.json`:

   ```bash
   .venv/bin/python -c "
   import json
   from shimkit.config.schema import ShimkitConfig
   schema = ShimkitConfig.model_json_schema()
   schema['\$schema'] = 'https://json-schema.org/draft/2020-12/schema'
   schema['title'] = 'shimkit configuration'
   print(json.dumps(schema, indent=2, ensure_ascii=False))
   " > config/shimkit.schema.json
   ```

3. Add `app.add_typer(<name>_app)` in `cli.py`.
4. Write `tests/test_tools_<name>.py`. Minimum coverage:
   - `Manager.boot()` smoke test (with mocked PM)
   - CLI `--help` lists subcommands
   - At least one subcommand's exit-code contract
5. Add `docs/tools/<name>.md` and link it from `docs/README.md`.
6. Add a CHANGELOG entry under `[Unreleased]`.

### Choosing the right primitives

By tool kind:

| Tool kind | Use |
|-----------|-----|
| Pure host shell-outs | `CommandRunner` + `Platform` (java, shell, dns) |
| Container orchestration | `DockerEnv` + `Platform`, preflight via `version.preflight(("docker",))` (db, stack, web, tls) |
| Manages a host daemon | `HostService.detect(platform)` (db --on-host) |
| Reads/writes a system file | atomic-write pattern: tempfile + `sudo install`, with a backup-on-mutate sidecar (hosts, web/nginx vhost apply, cron) |
| Wraps another shimkit tool | Import its `Manager` directly (framework laravel cron-install → cron) |

### Sub-app parents

Some tools have a sub-app parent (e.g. `framework laravel`, `web
nginx vhost`). The convention:

```
tools/<parent>/
  __init__.py
  commands.py       Parent Typer app — registers children
  <child>/
    __init__.py
    manager.py
    commands.py     Child Typer app
```

Sub-apps inherit the same five rules. Each child remains independently
testable, and the parent is mostly a Typer-glue file.

A tool joins shimkit only if it shares ≥ 2 of `Platform` / `Shell` /
`PackageManager` / `UI` / `Menu`. Otherwise it's a separate package.

## Shared subcommand surface

Every new tool's non-interactive subcommand accepts the same set of
flags, imported from `core/cli_flags.py`. Defining them once means
the surface is uniform across `dns`, `adguard`, `docker-clean`, and
any future tool — and the help text stays aligned.

| Flag             | Behaviour |
|------------------|-----------|
| `--dry-run, -n`  | Plan only; no mutation. Mandatory on every mutator. |
| `--json`         | Emit a single JSON document on stdout; chatter to stderr. |
| `--quiet, -q`    | Suppress non-error UI via `UI.set_quiet(True)`. Errors still print. |
| `--verbose, -v`  | Raise root shimkit logger to DEBUG. |
| `--yes, -y`      | Skip `[y/N]` prompts. Does NOT bypass severe-tier tokens. |
| `--force, -f`    | Bypass safety checks; logged loudly. |
| `--log-file PATH` | JSONL append; secret-looking keys redacted. |
| `--timeout SECS` | Network / wait timeout (default 30). |
| `--color={auto,always,never}` | Honours `NO_COLOR` env. |
| `--no-color`     | Shorthand for `--color=never`. |
| `--no-input`     | Never prompt (also when stdin is not a TTY). MODERATE-tier `[y/N]` prompts refuse with exit 1 rather than block. |

Exit codes are documented in `shimkit --help`:

| Code | Meaning |
|-----:|---------|
| 0   | ok / no-op |
| 1   | generic failure |
| 2   | Typer usage error |
| 64  | EX_USAGE (sysexits) |
| 69  | EX_UNAVAILABLE — service down, wrong platform, extra missing |
| 77  | EX_NOPERM — needs root / docker group |
| 78  | EX_CONFIG — invalid configuration |
| 130 | SIGINT |

## Optional dependency extras

The base `shimkit` install is intentionally lean. Each new tool ships
behind an optional extra so its dependencies (yaml, HTTP, psutil,
docker-py, dnspython) only land when used.

```toml
[project.optional-dependencies]
dns          = ["dnspython>=2.7"]
adguard      = ["ruamel.yaml>=0.18", "requests>=2.32", "psutil>=6.0"]
docker-clean = ["docker>=7.1"]
extra-tools  = ["dnspython>=2.7", "ruamel.yaml>=0.18",
                "requests>=2.32", "psutil>=6.0", "docker>=7.1"]
```

Each tool's `boot()` checks for its extra and exits **69** with a
message naming the exact install command if the extra is missing.

## Logging

`core/log.py` exposes `get_logger(name)` returning a logger
namespaced under `shimkit.<name>`. The root `shimkit` logger has a
`NullHandler` by default so importing the package emits nothing.

When the user passes `--log-file PATH`, `attach_file_handler(path)`
adds a JSONL `FileHandler` with a formatter that:

- Writes one JSON object per line.
- UTC ISO-8601 timestamp.
- Recursively redacts any dict key matching
  `password|passwd|pwd|secret|token|api[_-]?key|authorization`
  (case-insensitive) in the `extra={...}` payload.

No external telemetry. Local files only.

## Why this layout

- **Predictable** — every tool has the same shape. Reading one means
  you can navigate the others.
- **Bisectable** — tools can be added/removed without touching core
  or other tools.
- **Testable** — mocking happens at `CommandRunner` or `PackageManager`
  level; tests don't reach for `subprocess` directly.
- **Configurable** — what end users want to change lives in JSON;
  what implementers need to keep stable lives in code.
