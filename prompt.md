# shimkit — senior engineering brief

## Role

You wear four hats in this engagement, in priority order:

1. **Senior staff engineer** — own the architecture; reject anything
   that breaks shimkit's load-bearing rules. Read code before
   writing code. Cite `path:line` for every claim.
2. **Senior developer** — port the three shell scripts, refactor
   where the existing code is wrong, write the tests, write the
   docs. Strict typing, ruff clean, every PR-ready commit explains
   *why*.
3. **Cybersecurity engineer** — audit subprocess handling, sudo
   surface, file-path handling, secrets handling, supply chain,
   container hardening. Fix what you find. Document residual risk.
4. **DevOps engineer** — make the release machinery actually
   green-light end-to-end. Validate the CI matrix, the release
   workflow, Dependabot, branch protection, signing, SBOM. Close
   every pending item in `docs/shipping-checklist.md` that can be
   closed in-code.

Switch hats deliberately. State which hat you're wearing when the
work spans more than one.

---

## Mission

Seven phases, executed in order. Don't skip ahead. Phases 0–6 are
the macOS-side delivery; Phase 7 is the Ubuntu-side validation that
gates the `v0.2.0` tag.

| Phase | Goal | Host |
|------:|------|------|
| 0     | Read the codebase. No edits. Build a mental model. | any |
| 1     | Codebase audit + bug hunt (existing code, before any porting). Identify and fix. | any |
| 2     | Port the three shell scripts into native shimkit tools. | any |
| 3     | Security review across the whole project. Fix findings. | any |
| 4     | DevOps review + release-readiness. Close in-code blockers. | any |
| 5     | Validate (gates + manual smoke). Update docs + CHANGELOG. | macOS |
| 6     | Cleanup: delete the source shell scripts. | any |
| 7     | Ubuntu validation for `shimkit adguard` and `shimkit docker-clean` Linux paths. Gate the `v0.2.0` tag. | **Ubuntu 22.04 or 24.04** |

The Phase 6 cleanup is gated on Phases 0–5 passing. The `v0.2.0`
release is gated on Phase 7 passing on a real Ubuntu host.

---

## Invocation policy — non-negotiable

- Every command surfaced from any tool is invoked as
  `shimkit <tool> <action>`. NEVER as a standalone binary.
- `pyproject.toml::project.scripts` MUST contain ONLY the existing
  `shimkit = "shimkit.cli:app"` entry. Do not add `dns = ...`,
  `adguard = ...`, or `docker-clean = ...` console-script entries.
  This avoids collision with system commands (`dns(8)`, `docker`,
  `adguard-home` packages).
- Tool sub-app names registered via `app.add_typer(...)` are
  `dns`, `adguard`, `docker-clean`. Typer `name=` matches the
  human-typed token exactly. No aliases at the top level.
- Every example in every doc, help string, error message, and
  log line uses the full `shimkit <tool> <action>` form. Do not
  abbreviate to `<tool> <action>` even in tutorials.
- README, `docs/README.md`, and CHANGELOG all use the `shimkit`
  prefix consistently.

---

## Architecture rules — load-bearing

From `docs/architecture.md` and `CONTRIBUTING.md`. Restated because
every line you write must obey them.

1. Every tool builds on `shimkit.core` primitives. No tool
   re-implements subprocess, platform detection, package-manager
   dispatch, UI, or menus.
2. `CommandRunner` (`src/shimkit/core/command.py:37-71`) is the
   ONLY place that calls `subprocess`. Tests mock at this layer.
3. Config values come from `shimkit.config.get_config()`. Static
   ports, paths, version constants, supported lists go in
   `config/defaults.json` + `src/shimkit/config/schema.py`.
   Logic-critical regexes and idempotency markers stay in code.
4. Builder pattern: every tool exposes
   `Manager.create().boot().run()` (interactive menu) plus
   non-interactive methods called by Typer subcommands. Mirror
   `src/shimkit/tools/shell/manager.py`.
5. UI output ONLY through `shimkit.core.ui.UI`. No `print()`,
   no `typer.echo()`, no `rich.console.Console()` instantiations.
6. Strict typing. `mypy --strict` clean.
   `from __future__ import annotations` at the top of every module.
7. Ruff clean (E,F,W,I,N,UP,B,SIM,RUF; line-length 100).

A tool joins shimkit only if it shares ≥ 2 of `Platform` / `Shell`
/ `PackageManager` / `UI` / `Menu`. All three tools in this brief
qualify.

---

## Phase 0 — Read the codebase

Before any edit:

- Read `README.md`, `CONTRIBUTING.md`, `docs/architecture.md`,
  `docs/configuration.md`, `docs/release.md`,
  `docs/shipping-checklist.md`, `docs/tools/*.md`.
- Read every file under `src/shimkit/` end to end. Don't skim
  `cli.py`, `self_update.py`, `core/`, `config/`, `tools/java/`,
  `tools/shell/`.
- Read every test under `tests/`. Note the mock layer
  (`CommandRunner.run`), the autouse hermetic fixture in
  `tests/conftest.py`, and the `runner: CliRunner` fixture.
- Read `.github/workflows/ci.yml` and `release.yml` in full. Note
  the job DAG: `guard → build → publish-pypi → github-release →
  publish-ghcr → bump-homebrew-tap`.
- Read `Dockerfile`.

When done, write a single internal note (not committed) listing:

- 3-7 design decisions you observed.
- Any pattern that surprised you or felt inconsistent.
- Any TODOs / FIXMEs you saw.

This is your map. You will use it in Phase 1.

---

## Phase 1 — Codebase audit + bug hunt

Hat: senior staff engineer + cybersec.

### Static gates first

Run, capture output for the deliverable report:

```
.venv/bin/pytest -q --cov=shimkit --cov-report=term-missing
.venv/bin/ruff check src tests
.venv/bin/mypy src/shimkit
.venv/bin/python -m build
```

### Add new static gates

Add these to `pyproject.toml::optional-dependencies.dev` AND wire
them into CI (`.github/workflows/ci.yml`):

```
bandit>=1.7        # SAST for Python
pip-audit>=2.7     # CVE scan against installed deps
```

And run them now:

```
.venv/bin/bandit -r src/shimkit -ll
.venv/bin/pip-audit --skip-editable
```

### Code-level audit

Walk through every module in `src/shimkit/` with these questions:

- Does it call `subprocess` outside `core/command.py`?
  (`grep -rn 'import subprocess\|from subprocess' src/shimkit/`)
  Anything that's not `core/command.py` is a violation — fix it.
- Does it call `print(`, `typer.echo(`, or instantiate
  `rich.console.Console`? Replace with `UI.*`.
- Does it use `os.system` or `os.popen`? Replace.
- Does it pass user-controlled data into a string command line?
  If yes, audit for injection and switch to argv-list form.
- Does it use `shell=True` anywhere? Default answer should be
  *no*; if yes, justify in a one-line comment or remove.
- Does any function use unbounded recursion or read an entire
  large file into memory unnecessarily?
- Does any function return `Any` from typed code? Sharpen the type.
- Are there `# type: ignore` or `# noqa` annotations without a
  one-line reason comment at the site? Add the reason or remove
  the suppression.
- Are there dead imports / dead helpers (`vulture src/shimkit`
  if available)? Remove.

### Behavioral audit

- Does `shimkit doctor` (`src/shimkit/cli.py:121-158`) actually
  cover every tool's critical dependency? Add probes where it
  doesn't.
- Does `shimkit self-update` (`src/shimkit/self_update.py`)
  detect every install method documented in
  `docs/installation.md`? If `uv tool install`, `pipx install`,
  `brew`, `pip --user`, `curl install.sh`, and `docker run` are
  the documented six, the detector must cover all six.
- Does `shimkit config validate` reject every malformed input it
  should? Try: missing required key, wrong type, unknown key,
  extra root key.
- Does the user-config path respect `$XDG_CONFIG_HOME` AND
  `$SHIMKIT_CONFIG`?
- Does every tool's `boot()` gate on `Platform.is_supported` AND
  produce a useful error message naming the supported platforms?

### What you find, you fix

For each issue:

1. Cite `path:line`.
2. State the bug or the violation, with evidence.
3. Fix it. One conceptual change per commit.
4. Add or update a test that would have caught it.

Don't fix what isn't broken. Don't refactor for aesthetics. If
something is ugly but correct and load-bearing, leave it.

---

## Phase 2 — Port the three shell scripts

Hat: senior developer.

### Sources

| Script                                            | New tool                |
|---------------------------------------------------|-------------------------|
| `shell-scripts/fixdns.sh`                         | `shimkit dns` (macOS)   |
| `shell-scripts/fix-adguardhome-ports.sh`          | `shimkit adguard` (Linux) |
| `python/docker-nucker.sh`                         | `shimkit docker-clean` (all) |

Paths absolute:
- `/Users/imanimanyara/Artisan/projects/opensource/simtabi/shell-scripts/fixdns.sh`
- `/Users/imanimanyara/Artisan/projects/opensource/simtabi/shell-scripts/fix-adguardhome-ports.sh`
- `/Users/imanimanyara/Artisan/projects/opensource/simtabi/python/docker-nucker.sh`

### Per-tool package layout

```
src/shimkit/tools/<name>/
  __init__.py          # public re-exports
  models.py            # dataclasses / typed value objects
  manager.py           # Manager (create/boot/run + non-interactive methods)
  commands.py          # Typer subapp (<name>_app)
  <component>.py       # one or more domain modules
```

Wire up:
- `src/shimkit/cli.py` — `app.add_typer(dns_app)`,
  `app.add_typer(adguard_app)`, `app.add_typer(docker_clean_app)`.
- `src/shimkit/cli.py::doctor()` — one probe per new tool.

### Config additions

Add three sections to
`src/shimkit/config/schema.py::ToolsConfig`:

`DnsConfig`:
- `test_domains: list[str]` — default `["google.com", "cloudflare.com"]`
- `dns_servers: dict[str, list[str]]` — defaults `{"cloudflare":
  ["1.1.1.1", "1.0.0.1"], "google": ["8.8.8.8", "8.8.4.4"]}`
- `step_timeout_seconds: int` — default `5`
- `nuclear_confirm_token: str` — default `"REGENERATE"`
- `reset_confirm_token: str` — default `"RESET"`
- `backup_dir: str` — default
  `"~/Library/Application Support/shimkit/dns-backups"`

`AdGuardConfig`:
- `install_candidates: list[str]`
- `default_remap_dns_port: int` — `5353`
- `default_remap_http_port: int` — `8080`
- `target_ports: list[TargetPort]` — the 5-tuple list
- `safe_units_to_stop: list[str]` — `["dnsmasq.service",
  "bind9.service", "named.service", "unbound.service"]`
- `pihole_unit: str` — `"pihole-FTL.service"` (requires
  `--migrate-from-pihole` flag)
- `resolv_conf_mode: Literal["symlink","static"]` — default
  `"symlink"` (matches the AGH FAQ recommendation)
- `prefer_api_over_yaml: bool` — `True`
- `api_base_url: str` — `"http://127.0.0.1:80"`

`DockerCleanConfig`:
- `nuke_confirm_token: str` — `"DELETE"`
- `kubernetes_image_patterns: list[str]` —
  `["registry.k8s.io", "kube-", "kubernetes", "desktop-"]`
- `daemon_verify_timeout_seconds: int` — `30`
- `default_buildx_prune_all: bool` — `True`

After schema edits, regenerate `config/shimkit.schema.json` with
the snippet at `docs/architecture.md:158-167`.

### Optional dependency extras

In `pyproject.toml`:

```toml
[project.optional-dependencies]
dns          = ["dnspython>=2.7"]
adguard      = ["ruamel.yaml>=0.18", "requests>=2.32", "psutil>=6.0"]
docker-clean = ["docker>=7.1"]
extra-tools  = ["dnspython>=2.7", "ruamel.yaml>=0.18",
                "requests>=2.32", "psutil>=6.0", "docker>=7.1"]
```

Each tool's `manager.boot()` checks for its extra; emits
`UI.error(...)` and `sys.exit(69)` if missing, naming the exact
install command (`uv tool install 'shimkit[extra-tools]'` or
`pipx inject shimkit <pkgs>`).

### CLI design standards — apply to every new subcommand

Grounded in clig.dev. Encode via a shared Typer callback / typed
helper, not by copy-pasting flag definitions.

Noun-verb ordering everywhere (`shimkit dns flush`, not
`shimkit flush-dns`). Verbs consistent across tools: reads are
`show` / `list` / `status` / `inspect`; mutations are `set` /
`fix` / `prune` / `reset` / `rollback`.

Standard flags, applied uniformly to every subcommand:

```
-h, --help                   # Typer default
-v, --verbose                # raise logger to DEBUG
-q, --quiet                  # suppress non-error UI
-n, --dry-run                # plan only; mandatory for every mutator
-y, --yes                    # skip [y/N] prompts
-f, --force                  # bypass safety checks; logged loudly
    --json                   # single JSON doc on stdout; chatter to stderr
    --log-file PATH          # JSONL append
    --color=auto|always|never  # NO_COLOR env honoured (any non-empty)
    --no-color               # alias for --color=never
    --timeout SECONDS        # for any network / wait operation
    --config PATH            # override shimkit user-config path
    --no-input               # never prompt (also when stdin not a TTY)
```

Exit codes (document in `shimkit --help`):

```
0    ok / no-op
1    generic failure
2    Typer usage error
64   EX_USAGE         bad arguments (sysexits.h)
69   EX_UNAVAILABLE   service down / wrong platform / extra missing
77   EX_NOPERM        needs root / docker group
78   EX_CONFIG        invalid configuration
130  SIGINT           interrupted by user
```

Progress / spinners: suppress when `not sys.stdout.isatty()`,
`--quiet`, `--json`, `--no-color`, or `CI=true`. `--json` mode
emits a single object or array on stdout, with every other line
going to stderr.

Confirmation tiers (clig.dev's "make it hard to confirm by
accident" pattern):

- MILD: proceed.
- MODERATE: `[y/N]` prompt; `--yes` bypasses. Examples:
  `shimkit dns set`, `shimkit adguard ports set`,
  `shimkit docker-clean prune-*`.
- SEVERE: user types a literal token via `--confirm <token>`;
  `--yes` alone does NOT suffice. Tokens come from config:
  `dns reset` → `RESET`; `dns fix --nuclear` → `REGENERATE`;
  `docker-clean nuke` → `DELETE`.

Help text: every command has a one-line `short_help` AND a
multi-line `help` containing 1–3 concrete examples. Per clig.dev,
examples beat prose.

Config precedence (clig.dev verbatim): flags > env > user config
> bundled defaults. Secrets (AGH API password) come from env
only. Never log secrets. Never accept secrets as CLI flags.

Experimental commands: hide behind `SHIMKIT_EXPERIMENTAL=1` env
AND Typer's `hidden=True`. Group in `--help` via
`rich_help_panel="Experimental"`. Prefix `short_help` with
`[experimental]`.

### Per-tool command surface

#### A) `shimkit dns` — macOS DNS resolver recovery

```
shimkit dns                          # interactive menu
shimkit dns diagnose                 # read-only; scutil --dns + chain
shimkit dns flush                    # cache + mDNSResponder HUP only
shimkit dns fix [--start-at N] [--stop-at N] [--skip-nuclear]
                                     # 6-step escalation
shimkit dns show                     # configured DNS for active service
                                     # (alias: dns servers show)
shimkit dns set <ip>...              # set servers; --service "Wi-Fi" override
shimkit dns reset --confirm RESET    # restore DHCP (severe)
shimkit dns test [domain...]         # resolve via dscacheutil + dig + curl
shimkit dns profile list             # installed encrypted-DNS profiles
                                     # via `profiles list`
shimkit dns rollback                 # restore most recent plist backup
shimkit dns diagnostics export       # bundle to PATH (replaces ~/Desktop file)
```

Platform gate: `Platform.is_macos`. Exit `69` on Linux/WSL with
a clear "this tool targets macOS" message.

#### B) `shimkit adguard` — AdGuard Home port-conflict fixer

```
shimkit adguard                              # interactive menu
shimkit adguard scan                         # read-only; ports + owners + classify
shimkit adguard fix [--dry-run]
       [--install PATH] [--remap-only]
       [--dns-cleanup-only]
       [--migrate-from-pihole]
shimkit adguard verify                       # loopback DNS + /control/status
shimkit adguard ports show
shimkit adguard ports set --dns N --http N
shimkit adguard config validate              # AdGuardHome --check-config
shimkit adguard service {start,stop,restart,status}
shimkit adguard logs [-n N] [--follow]       # journalctl -u AdGuardHome
shimkit adguard rollback                     # restore latest backups
```

Platform gate: `Platform.is_linux`. Exit `69` on macOS/WSL.

Auth for API calls: `ADGUARD_USER` / `ADGUARD_PASS` env vars or
`~/.config/shimkit/adguard.toml`. Never as CLI flags.

#### C) `shimkit docker-clean` — Docker resource cleanup

```
shimkit docker-clean                         # interactive menu
shimkit docker-clean status                  # docker system df --format json
shimkit docker-clean quick                   # stop containers + system prune
shimkit docker-clean custom                  # checkbox menu
shimkit docker-clean nuke --confirm DELETE   # severe
shimkit docker-clean restart                 # daemon restart only
shimkit docker-clean stop-all                # stop all running containers
shimkit docker-clean prune-images
shimkit docker-clean prune-volumes
shimkit docker-clean prune-networks
shimkit docker-clean prune-builders          # iterates docker buildx ls
shimkit docker-clean inspect <kind>          # containers|images|volumes|
                                             #   networks|cache
shimkit docker-clean orphans                 # dangling images + unused volumes
shimkit docker-clean compose-down PATH [--volumes]
shimkit docker-clean schedule [--interval=weekly] [--out=PATH]
                                             # print (do not install) a
                                             # launchd plist / systemd
                                             # timer / cron line
```

Daemon ops use the `docker-py` SDK. Shell out ONLY for
`docker desktop *` (no SDK), `docker compose down`, and
`docker system df --format json`.

### Bugs to fix in the port (not carry over)

Confirmed by re-read. Don't replicate.

`fixdns.sh`:
- `:12` — `set -u` without `-e` or `pipefail`. Python has
  exceptions; no equivalent footgun.
- `:64-71` — spinner indexes UTF-8 box chars by byte under bash
  3.2; prints garbage. Use Python.
- `:81-84` — `timeout 3 nslookup`: `timeout(1)` not on stock
  macOS. Use `nslookup -timeout=3` (BSD built-in).
- `:99` — `ping -W 2000` flag semantics differ macOS vs Linux.
  Use Python socket connect timeout.
- `:106-131` — `detect_service` uses `grep -E '\d+'`; BSD grep
  doesn't support `\d`. Falls through to fallback always.
  Re-implement with Python `re`.
- `:148-157` — sudo keepalive started before `EXIT` trap. SIGINT
  race. Use Python `atexit` + signal handler.
- `:249-268`, `:331-333` — `setairportpower "$INTERFACE"`
  silently no-ops if interface is not Wi-Fi. Branch on
  `networksetup -listallhardwareports` first.
- `:365`, `:383` — `$(date ...)` evaluated twice; midnight
  boundary drift. Cache once.

`fix-adguardhome-ports.sh`:
- `:35`, `:241` — header says "bash 4+" but shebang doesn't
  enforce; `declare -A` would die under macOS bash 3.2. Add a
  guard (moot in Python).
- `:73` — `exec | tee` redirection eats subcommand exit codes.
  Use Python `logging` with a `FileHandler`.
- `:165-180` — runs DNS cleanup even when AGH absent. Python:
  exit `69` unless `--dns-cleanup-only` is set.
- `:189-225` — awk yaml port extractor brittle (indent
  heuristic on first non-blank line; breaks on comment blocks).
  Use `ruamel.yaml`.
- `:277-279` — `ss -H` fallback strips wrong char in older
  iproute2. Prefer `psutil.net_connections('inet')`.
- `:286-296` — awk extracts process info; silently skips
  kernel-thread-held ports. Document as known limitation.
- `:394-396` — NetworkManager warning only; does NOT write the
  `dns=none` drop-in. Python MUST write
  `/etc/NetworkManager/conf.d/90-shimkit-adguardhome.conf` and
  `nmcli general reload`.
- `:462-545` — yaml edit happens while AGH may be running; AGH
  overwrites yaml on shutdown per its wiki. Python MUST
  `systemctl stop AdGuardHome` before yaml edit; prefer HTTP
  control API.

`docker-nucker.sh`:
- `:202`, `:214` — `local x=$(cmd)` masks command exit code.
  Python: explicit exception handling.
- `:473`, `:496`, `:537`, `:583` — `docker X $(docker ...)`
  zero-arg footgun. SDK loop instead.
- `:518` — `grep "registry.k8s.io\|kube-..."` portability.
  Replaced by SDK image enumeration.
- `:531` — `for image in $(...)` word-splits image tags with
  whitespace. SDK handles.
- `:608`, `:757` — `((var++))` under `set -e` with starting
  value 0 exits non-zero. `verify_docker` currently runs at most
  once. Python: normal arithmetic; `verify_docker` becomes a
  real loop.
- `:632-643` — `local output=$(...); if [ $? -eq 0 ]` — `$?`
  reads `local`'s exit code, NOT the command's. ALWAYS reports
  success. Build-cache pruning success/failure currently cannot
  be detected. **HIGH severity.**
- `:655-657` — same bug for `system_prune`. **HIGH severity.**
- `:673-681` — uses `osascript` for Docker Desktop. Use
  `docker desktop restart` (Docker Desktop 4.37+) with osascript
  fallback for older.
- `:683-738` — add buildx-builder enumeration before
  `builder prune -af`; current command misses cache held by
  named builders.

### Core helpers — only if shared ≥ 2 tools

`src/shimkit/core/systemd.py`:
- `Systemd.is_active(unit)`, `.stop(unit)`, `.start(unit)`,
  `.restart(unit)`, `.write_drop_in(unit, name, body)`,
  `.reload()`.
- Used by `adguard` (resolved + AGH) and `docker-clean` (Linux
  daemon restart).

`src/shimkit/core/json_event.py`:
- Typed `Event` model and `emit_json(events)` printer used by
  all three tools for `--json` mode.

`src/shimkit/core/log.py`:
- `get_logger(name)` wiring stdlib `logging`. Default
  `NullHandler`. `--log-file PATH` attaches a JSONL FileHandler
  (UTC ISO-8601 timestamp, level, tool, event, payload).
- NO external telemetry. Local files only.

Single-tool helpers stay inside the tool package
(`tools/dns/scutil.py`, `tools/adguard/agh_api.py`, etc.).

### Tests — mandatory minimum per new tool

`tests/test_tools_<name>.py`, mirroring
`tests/test_tools_shell.py`:

- `Manager.boot()` success with mocked `CommandRunner` +
  `Platform`.
- `Manager.boot()` exits `69` on wrong platform.
- Boot exits `69` when an optional extra is missing.
- Every non-interactive subcommand: success path + at least one
  failure path with the right exit code.
- CLI `--help` lists every subcommand.
- `--json` mode emits parseable JSON for at least one command.
- `--dry-run` makes no destructive calls.
- Severe-tier commands abort without `--confirm`.

Mock at `CommandRunner.run`, `Platform(...)`, `docker.from_env()`,
`requests.Session`. NEVER touch a real DNS resolver, systemd,
docker daemon, or AGH API.

### Docs

Create:
- `docs/tools/dns.md`
- `docs/tools/adguard.md`
- `docs/tools/docker-clean.md`

Style: match `docs/tools/java.md` and `docs/tools/shell.md`. Each
file contains tagline, commands table, 3–5 numbered example
sessions, configuration section with the relevant defaults.json
snippet, exit codes table, platform-support matrix, troubleshoot
section (3–5 common failures + the doctor-probe output that
indicates each), and an origin note pointing to the bash script
that was replaced.

Update:
- `README.md` — add three lines to the Tools section, each
  using the `shimkit <tool>` form.
- `docs/README.md` — add three rows to the topic table.
- `CHANGELOG.md` — Unreleased section: "Added: dns, adguard,
  docker-clean tools (Python ports of the shell-scripts/*
  utilities). The shell versions are removed."
- `docs/installation.md` — note the optional extras and their
  install commands.
- `docs/configuration.md` — document new config sections with
  JSON snippets.

---

## Phase 3 — Security review

Hat: cybersec.

Use real tools, not vibes. Capture findings in a working note;
fix what can be fixed in-code; surface what can't to the
maintainer.

### Automated scans

```
.venv/bin/bandit -r src/shimkit -ll        # SAST
.venv/bin/pip-audit --skip-editable        # CVE in deps
hadolint Dockerfile                        # container linter
```

Add `bandit` and `pip-audit` as CI jobs (parallel to `pytest`)
in `.github/workflows/ci.yml`. Fail the build on HIGH severity.

### Manual review checklist

For each item below: state your finding, fix it, and add a test
or a comment justifying the residual risk.

1. **Subprocess injection.**
  - `grep -rn 'shell=True' src/shimkit/` — should be empty.
  - Confirm every `CommandRunner.run` call passes a list, not a
    string.
  - Confirm no `f"{cmd} {user_input}"` constructions.

2. **Sudo surface.**
  - `grep -rn 'sudo' src/shimkit/` — every call must come
    through `sudo_prefix()` in `core/command.py:74-86`.
  - `dns` and `adguard` need root. `boot()` must check
    `os.geteuid() == 0` (Linux) / a sudo probe (macOS) and exit
    `77` with a clear message if not root.
  - Never elevate silently; never persist a sudo timestamp
    beyond the session.

3. **File-path handling.**
  - Backup paths: `dns` writes to a `backup_dir` config value.
    Resolve via `Path.expanduser().resolve()` and refuse paths
    outside `~`. No symlink-following on write.
  - `adguard` writes to `/etc/systemd/resolved.conf.d/` and
    `/etc/NetworkManager/conf.d/`. Validate the file name; do
    not interpolate user-controlled data into the file body.
  - Use `os.O_CREAT | os.O_EXCL` for new files; refuse to
    overwrite existing without an explicit `--force`.

4. **Secrets handling.**
  - AGH API password: env-only (`ADGUARD_PASS`). Never log;
    never echo in error messages; redact in `--verbose`.
  - When writing `--log-file`, scrub `Authorization` headers
    and any `*_PASS` env values.
  - `--json` output must not embed secrets.

5. **HTTP client (`requests`).**
  - `verify=True` everywhere. No `verify=False`. No
    `urllib3.disable_warnings()`.
  - Every call has an explicit `timeout` (default `--timeout`
    value).
  - No basic-auth in URL (`https://user:pass@host`). Use the
    `auth=` kwarg.

6. **YAML parsing.**
  - `ruamel.yaml` with `typ='rt'` (round-trip). Never
    `yaml.unsafe_load`. Never `yaml.load` without a `Loader=`.

7. **Race conditions.**
  - `/etc/resolv.conf` swap: write to a tempfile in `/etc/`
    (same filesystem) then `os.replace()`. Don't `rm` then
    `open`.
  - AGH yaml: stop AGH service, edit, verify, start. Don't
    skip the verify step.

8. **Supply chain.**
  - All deps pinned at minimum-version floors with `>=` (already
    done). Hash-pinned in CI's `pip install --require-hashes`
    if practical.
  - Released wheels carry an SPDX SBOM and `actions/attest-build-
    provenance` signatures (verifiable via `gh attestation verify`).
  - Confirm `pyproject.toml` doesn't pull from anywhere except
    PyPI (no `tool.uv.sources` pointing at a fork).

9. **Container hardening.**
  - `Dockerfile` runs as non-root (`USER` directive). Confirm.
  - Base image is the minimum needed (`python:3.13-slim` or
    `gcr.io/distroless/python3`). Confirm and document the
    trade-off.
  - No build secrets in layers (`docker history` clean).
  - `HEALTHCHECK` present.
  - Image signed via GHCR's `gh attestation` (already in
    `release.yml`).

10. **Logging discipline.**
  - No PII in logs without redaction.
  - No tokens, no passwords, no IP addresses of internal
    networks beyond what the user pointed the tool at.
  - `--log-file` is opt-in; never write to global paths by
    default.

11. **Permissions on files written.**
  - `0o600` for anything containing secrets-adjacent data.
  - `0o644` for config files; `0o644` for `/etc/*` drop-ins.
  - Never `0o777`.

12. **Self-update path.**
  - `src/shimkit/self_update.py` — verify the download
    provenance. Check signature or sha256 against the release
    manifest before exec.
  - Refuse to self-update over an install method that wasn't
    detected.

### Write `SECURITY.md` updates if needed

If your scan turns up disclosure-relevant issues, update
`SECURITY.md` to reflect them. The disclosure address stays at
`opensource@simtabi.com`.

---

## Phase 4 — DevOps + release readiness

Hat: devops.

Goal: every item in `docs/shipping-checklist.md` that can be
closed in-code is closed; the rest are clearly flagged as
user-action with the exact command.

### CI matrix

`.github/workflows/ci.yml` — confirm and extend:

- Matrix: macOS-latest + ubuntu-latest × Python 3.10, 3.11, 3.12,
  3.13. (Per shipping-checklist line 1.3.)
- Jobs:
  - `lint` (ruff)
  - `type` (mypy)
  - `test` (pytest + coverage)
  - `security` (bandit + pip-audit) — ADD
  - `shellcheck` — confirm exists
  - `hadolint` (Dockerfile) — ADD
  - `build` (`python -m build`; upload sdist+wheel as artifacts)
  - `smoke` — install the built wheel in a clean venv on macOS
    + Ubuntu and run `shimkit doctor`, `shimkit --help`,
      `shimkit version`. ADD if missing.
- Coverage threshold: fail under 85% lines on `src/shimkit/`.
  Add the threshold to `pyproject.toml::tool.pytest.ini_options`
  or as a `coverage` step.

### Release workflow

`.github/workflows/release.yml` — confirm:

- `guard` job validates tag against
  `pyproject.toml::project.version` AND
  `src/shimkit/__init__.py::__version__`.
- `publish-pypi` uses OIDC trusted-publisher (no token).
- `github-release` uploads sdist + wheel + sha256.
- `publish-ghcr` builds multi-arch (linux/amd64, linux/arm64),
  signs with `gh attestation`, pushes.
- `bump-homebrew-tap` opens a PR against `simtabi/homebrew-tap`
  using `TAP_GITHUB_TOKEN`.

If any step is missing, add it. Cite `path:line` in the commit
message.

### Branch protection & merge hygiene

These are user actions, not in-code; surface them in the
deliverable report:

- Require `lint`, `type`, `test`, `security`, `build` to pass
  before merge.
- Require linear history.
- Require signed commits if the org policy uses signing.

### Pre-commit hooks

Add `.pre-commit-config.yaml` at the repo root with:

- `ruff` (lint + format)
- `mypy` (optional, slow — gate behind `manual` stage)
- `shellcheck` for any `*.sh`
- `check-yaml`, `check-json`, `check-toml`, `end-of-file-fixer`,
  `trailing-whitespace` from `pre-commit-hooks`

Document the `pre-commit install` step in `CONTRIBUTING.md`.

### Dependabot

`.github/dependabot.yml` — confirm and extend if needed:

- `pip` weekly Monday 06:00 America/New_York.
- `github-actions` weekly Monday 06:00.
- `docker` weekly Monday 06:00.

If `docker` isn't covered, add it.

### SBOM + signatures

Add to `release.yml`:

- Generate SBOM (`anchore/sbom-action` or `syft`) on the wheel
  and the container image; upload both as release assets.
- Already-present `gh attestation` covers signing.

### Container image

`Dockerfile` — confirm or fix:

- Multi-stage (build + runtime).
- Runtime stage is non-root (`USER shimkit`).
- Base image pinned by digest (`python:3.13-slim@sha256:...`),
  not just by tag.
- `HEALTHCHECK CMD ["shimkit", "version"]`.
- `LABEL` set: `org.opencontainers.image.source`,
  `org.opencontainers.image.licenses`,
  `org.opencontainers.image.description`.

### Installation channels

shimkit installs via uv/pipx/pip/brew directly — no custom installer
script. Verify the published wheels carry an SBOM, the container
image has a signed attestation, and `shimkit self-update` correctly
dispatches per install method.

---

## Phase 5 — Validation

Hat: all four, in rotation.

### Quality gates — run all; report each

```
.venv/bin/pytest -q --cov=shimkit --cov-report=term-missing
.venv/bin/ruff check src tests
.venv/bin/mypy src/shimkit
.venv/bin/bandit -r src/shimkit -ll
.venv/bin/pip-audit --skip-editable
.venv/bin/python -m build
hadolint Dockerfile
```

Don't claim success on a partial run. If a gate is yellow,
explain why. If a gate is red, fix it.

### Manual smoke

Do this. Record host. If you can't run a path, say so honestly;
do not claim it was validated.

macOS:
```
shimkit --help
shimkit doctor
shimkit version
shimkit dns diagnose
shimkit dns flush
shimkit dns test
shimkit docker-clean status
shimkit docker-clean prune-builders --dry-run
NO_COLOR=1 shimkit dns diagnose
shimkit dns diagnose --json | jq .
```

Ubuntu (host with AGH installed):
```
shimkit adguard scan
shimkit adguard verify
shimkit docker-clean status
shimkit doctor
```

Both:
```
shimkit --help shows the three new sub-apps
shimkit doctor includes the three new probes
```

### Final doc + changelog sweep

- `CHANGELOG.md` Unreleased section is accurate.
- `README.md` Tools list matches reality.
- `docs/README.md` topic table matches reality.
- `docs/shipping-checklist.md` items you closed are marked done;
  items you didn't are clearly user-action.

---

## Phase 6 — Cleanup (gated)

Only after every prior phase passes. Order matters.

```
rm -i /Users/imanimanyara/Artisan/projects/opensource/simtabi/shell-scripts/fix-adguardhome-ports.sh
rm -i /Users/imanimanyara/Artisan/projects/opensource/simtabi/shell-scripts/fixdns.sh
rm -i /Users/imanimanyara/Artisan/projects/opensource/simtabi/python/docker-nucker.sh
rmdir /Users/imanimanyara/Artisan/projects/opensource/simtabi/shell-scripts/   # if empty (ignore .DS_Store)
```

Rules:
- `rm -i`, not `rm -f` or `rm -rf`. The user vets each delete.
- Don't delete `/Users/imanimanyara/Artisan/projects/opensource/simtabi/python/` — it contains `sm-downloader`, unrelated.
- Don't touch any `.DS_Store` above those paths.
- Don't commit. Don't tag. Don't push. Leave the tree dirty.

---

## Phase 7 — Ubuntu validation (v0.2.0 sign-off)

Hat: senior developer + devops.

**Why this phase exists.** Phases 0–6 ran on macOS. Two tools have
Linux paths that the macOS session could not exercise end-to-end:

- `shimkit adguard` — Linux-only. The `adguard-integration` CI job
  exercises `scan`, `verify`, `ports show`, `fix --dry-run`,
  `ports set --dry-run` against a real AGH on ubuntu-latest. It
  does NOT exercise the **mutating** paths (writing the
  `systemd-resolved` drop-in, the NetworkManager `dns=none`
  drop-in, the yaml-fallback ports set with AGH stopped/started,
  `rollback`, pi-hole migration). Those need a real Ubuntu desktop.
- `shimkit docker-clean` — cross-platform. macOS exercised the
  Docker Desktop path. The Linux/systemd `restart` path and the
  `compose-down` integration weren't manually exercised.

This phase closes those gaps before tagging `v0.2.0`.

### Prerequisites

1. An Ubuntu 22.04 LTS or 24.04 LTS host (matches the CI matrix).
   A VM, a dedicated Linux desktop, or a fresh cloud instance all
   work. WSL is **not** sufficient — `systemd-resolved` and
   NetworkManager don't behave there the way they do on bare
   Ubuntu.
2. A user account with `sudo`. Several `adguard fix` paths write
   to `/etc/*` and control systemd units.
3. Network reachability for the Ubuntu mirrors, GitHub releases
   (AGH binary), and PyPI.
4. **Optional but recommended:** a snapshot or recovery path. The
   `fix` flow stops `systemd-resolved` and rewrites
   `/etc/resolv.conf`. The provided `rollback` will restore it,
   but a VM snapshot is a faster panic button.

### Step 1 — Build verification on Ubuntu

Confirm the wheel and container image build cleanly on the target
platform (not just on the CI runner image).

```bash
git clone https://github.com/simtabi/shimkit
cd shimkit
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,extra-tools]"

# 1. Wheel build
python -m build
ls -la dist/
# Expect: shimkit-X.Y.Z-py3-none-any.whl + shimkit-X.Y.Z.tar.gz

# 2. Install built wheel into a clean venv (mirrors the smoke CI job)
python3 -m venv /tmp/shimkit-smoke
/tmp/shimkit-smoke/bin/pip install "dist/$(ls dist/*.whl)[extra-tools]"
/tmp/shimkit-smoke/bin/shimkit version
/tmp/shimkit-smoke/bin/shimkit --help
/tmp/shimkit-smoke/bin/shimkit doctor
# Expect: 0.1.0 / all 5 tools listed / doctor probes incl. adguard + docker

# 3. Container image
docker build -t shimkit:local .
docker run --rm shimkit:local version
docker run --rm shimkit:local doctor
# Expect: same outputs as above; image runs as the `shimkit` user.

# 4. Container HEALTHCHECK
docker run -d --name shimkit-health shimkit:local sleep 60
sleep 35  # let HEALTHCHECK fire
docker inspect --format='{{.State.Health.Status}}' shimkit-health
# Expect: "healthy"
docker rm -f shimkit-health
```

### Step 2 — `shimkit adguard` mutating-path validation

For each scenario below: capture stdout, stderr, and the relevant
system state before/after. Save a transcript so the v0.2.0 release
PR can link to it.

#### 2a. AGH present, systemd-resolved holds port 53 (the canonical case)

```bash
# Confirm pre-state
sudo systemctl is-active systemd-resolved   # expect: active
sudo ss -tulnp | grep -E ':(53|80|443)\b'   # expect: resolved on :53

# Install AGH if not already installed (use the official one-liner
# from https://adguard-dns.io/kb/adguard-home/getting-started/).

# Read-only preview
sudo shimkit adguard scan --json | tee /tmp/agh-scan-before.json
sudo shimkit adguard fix --dry-run --json | tee /tmp/agh-fix-plan.json
# Expect: scan reports the systemd-resolve conflict; fix plan lists
# steps `resolved`, `restart`; nothing applied.

# Apply
sudo shimkit adguard fix --json | tee /tmp/agh-fix-apply.json

# Confirm post-state
ls -la /etc/systemd/resolved.conf.d/90-shimkit-adguardhome.conf
cat   /etc/systemd/resolved.conf.d/90-shimkit-adguardhome.conf
readlink -f /etc/resolv.conf      # expect: /run/systemd/resolve/resolv.conf
                                   # (symlink mode — the AGH FAQ recommendation)
sudo systemctl is-active systemd-resolved
sudo ss -tulnp | grep -E ':53\b' | head -5
# Expect: AdGuardHome owns :53/tcp + :53/udp; systemd-resolved still
# running with stub disabled.

# Loopback verify
shimkit adguard verify --json | tee /tmp/agh-verify.json
# Expect: api: true, loopback_dns: true
```

#### 2b. NetworkManager is also active (Ubuntu Desktop)

```bash
# Confirm NM is the canary
sudo systemctl is-active NetworkManager
# After fix runs:
ls /etc/NetworkManager/conf.d/90-shimkit-adguardhome.conf
cat /etc/NetworkManager/conf.d/90-shimkit-adguardhome.conf
nmcli general status
# Expect: the dns=none drop-in present; nmcli reload completed.

# Force an interface event and confirm resolv.conf survives.
sudo nmcli connection down "<your-active-connection>"
sudo nmcli connection up "<your-active-connection>"
readlink -f /etc/resolv.conf
# Expect: still pointing at /run/systemd/resolve/resolv.conf (or
# `nameserver 127.0.0.1` if you used resolv_conf_mode=static).
```

#### 2c. YAML fallback (API unreachable)

```bash
# Sabotage the API auth so prefer_api_over_yaml falls through.
unset ADGUARD_USER ADGUARD_PASS

# Read current ports
sudo shimkit adguard ports show --json
# Expect: dns/http ports per yaml.

# Change them with the yaml-fallback path
sudo shimkit adguard ports set --dns 5353 --http 8080
# Expect: AGH stopped, yaml edited (atomic rename), AGH started.
# A backup file should land next to the yaml.

ls -la $(dirname $(sudo find /opt /var/lib /etc -name AdGuardHome.yaml 2>/dev/null | head -1))/AdGuardHome.yaml.bak-*
sudo shimkit adguard ports show --json
# Expect: dns_port=5353, http_port=8080.

# Diff the yaml: only the two port keys should have changed; comments
# and ordering should be preserved (ruamel.yaml round-trip).
diff <(sudo cat /path/to/backup) <(sudo cat /path/to/AdGuardHome.yaml)
```

#### 2d. Rollback

```bash
sudo shimkit adguard rollback
# Expect: latest yaml backup restored; latest /etc/resolv.conf.bak-*
# restored if one exists; AGH restarted via systemctl.

sudo shimkit adguard ports show --json
# Expect: ports back to their pre-set values.
```

#### 2e. Pi-hole co-existence

```bash
# Only run this if you can safely install pi-hole on the test host.
# Pi-hole is a similar DNS gatekeeper — shimkit refuses to stop it
# without --migrate-from-pihole.

# With pi-hole installed but AGH NOT yet stopping it:
sudo shimkit adguard fix
# Expect: skip:pihole-FTL.service event in the output, with note
# "pi-hole is the conflict — pass --migrate-from-pihole to stop it."

sudo shimkit adguard fix --migrate-from-pihole
# Expect: stop+disable of pihole-FTL.service.
```

#### 2f. Service + logs + config-validate

```bash
sudo shimkit adguard service status        # expect: active/enabled/exists triple
sudo shimkit adguard service restart       # expect: exit 0
sudo shimkit adguard logs -n 50            # expect: journalctl output
sudo shimkit adguard config validate       # expect: exit 0 if yaml valid
```

### Step 3 — `shimkit docker-clean` Linux path

```bash
# Daemon-side smoke (mirrors the macOS run from Phase 5)
shimkit docker-clean status --json | jq .

# Status when daemon is down — should exit 69
sudo systemctl stop docker
shimkit docker-clean status                # expect: exit 69
sudo systemctl start docker

# Daemon restart through systemd
sudo shimkit docker-clean restart
# Expect: systemctl restart docker; daemon comes back; exit 0.
# (This is the path that the bash version's ((attempt++)) bug
# silently broke.)

# Compose-down for a real project
mkdir /tmp/compose-smoke && cd /tmp/compose-smoke
cat > compose.yml <<'YAML'
services:
  web:
    image: nginx:alpine
    ports: ["8080:80"]
YAML
docker compose up -d
shimkit docker-clean compose-down compose.yml --volumes
docker compose ps                          # expect: empty
```

### Step 4 — Sign-off criteria for `v0.2.0`

Mark each as PASS/FAIL/SKIP in the release PR description. **All
PASS or SKIP — no FAIL — to cut the tag.**

| Check | Source | Notes |
|-------|--------|-------|
| All CI gates green on `main` | GitHub Actions | `test`, `security`, `build`, `smoke`, `dockerfile-hadolint`, `adguard-integration` |
| `python -m build` on Ubuntu | Step 1.2 above | sdist + wheel produced |
| `docker build` on Ubuntu | Step 1.3 above | image builds + runs |
| `HEALTHCHECK` reports `healthy` | Step 1.4 | 30s observation |
| `adguard fix` end-to-end (systemd-resolved case) | Step 2a | yaml backup + drop-in + symlink + verify pass |
| `adguard fix` end-to-end (NetworkManager case) | Step 2b | nm drop-in + reload + survives link event |
| `adguard ports set` yaml fallback | Step 2c | atomic edit, ruamel preserves comments |
| `adguard rollback` | Step 2d | backups restored, daemon restarted |
| Pi-hole migration | Step 2e | optional; skip if no pi-hole environment |
| `adguard service|logs|config validate` | Step 2f | exit codes 0 |
| `docker-clean status`, `restart`, `compose-down` | Step 3 | Linux daemon path green |

### Step 5 — Capture diagnostics for the PR

Attach to the v0.2.0 release PR:

1. The JSON outputs from steps 2a, 2c, 2d, and 3 (so reviewers can
   inspect step-by-step events without re-running).
2. `journalctl -u AdGuardHome -n 200` immediately after step 2a's
   `fix` apply.
3. The diff from step 2c showing only port-key changes.
4. The `git status --short` from the workstation that performed
   the validation, in case any unexpected files got touched.
5. The `shimkit version`, `shimkit doctor`, and `uname -a` output
   from the Ubuntu host.

### Step 6 — Update CHANGELOG.md

Move the `Unreleased` section to `[0.2.0] — YYYY-MM-DD` once the
above passes. Then follow the existing release path documented in
`docs/release.md`:

```bash
# Once everything above is PASS:
git tag v0.2.0
git push origin v0.2.0
```

The release workflow takes it from there.

### What this phase does NOT cover

- Hostile-network scenarios (DNS exfiltration filters, captive
  portals). Beyond scope — shimkit is a developer tool, not a
  network-security audit subject.
- Distro coverage beyond Ubuntu 22.04 / 24.04. Other distros
  (Debian, Fedora, Arch) will work but aren't formally validated;
  the architecture is generic. Treat first-class support for any
  new distro as its own follow-up issue.
- Real-AGH-running tests that mutate `/etc/resolv.conf`. The
  `adguard-integration` CI job runs AGH on non-default ports
  (5300/8000) so it doesn't fight the runner's `systemd-resolved`;
  the resolv.conf rewrite path is exercised here, not in CI.

---

## DO NOT

- Commit, tag, or push.
- Add a top-level command outside the three named.
- Add `console_scripts` beyond the existing `shimkit = ...`.
- Add a logging or telemetry SaaS dependency.
- Bypass `CommandRunner` for "just one quick subprocess".
- Paraphrase paths or line numbers from memory. Read or grep first
  and cite `path:line` in commit bodies.
- Delete the source scripts before Phase 6.
- Use AI-tells in commit messages or docs: `leverage`, `powerful`,
  `robust`, `comprehensive`, `seamless`, `essentially`, `note that`,
  `simply,`.
- Use `--no-verify` to skip hooks; fix the underlying issue.
- Make destructive changes (force-push, reset --hard, branch -D)
  without explicit user approval.

---

## Deliverable report

At the end, print:

1. Exit code of each quality gate.
2. Number of new tests added (`git diff --stat tests/ | tail -1`).
3. LoC added/removed (`git diff --shortstat`).
4. Coverage delta on `src/shimkit/`.
5. List of bugs found and fixed in the existing codebase
   (Phase 1) — one line each, with `path:line`.
6. List of security findings from Phase 3 — fixed vs. flagged.
7. List of DevOps items from Phase 4 — closed in-code vs.
   user-action.
8. Manual-smoke results: which host, which commands, success/fail.
9. Confirmed list of source files deleted in Phase 6.
10. Anything you skipped or could not verify, with reason.
