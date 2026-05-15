# shimkit — target architecture (post-migration, v0.5.0+)

Builds on [`architecture-current.md`](./architecture-current.md). Two
new cross-cutting primitives + four new tools, none breaking changes.

## Diff vs current

```
src/shimkit/
├── core/
│   ├── command.py            (unchanged)
│   ├── ui.py                 (unchanged)
│   ├── menu.py               (unchanged)
│   ├── pkgmgr.py             (unchanged)
│   ├── platform.py           (unchanged)
│   ├── shell.py              (unchanged)
│   ├── systemd.py            (unchanged)
│   ├── log.py                (unchanged)
│   ├── json_event.py         (unchanged)
│   ├── cli_flags.py          (unchanged)
│   ├── docker.py             ★ NEW — Docker SDK helper, naming conventions, lifecycle
│   └── version.py            ★ NEW — VersionConstraint, detect(), validate(), Result
├── config/
│   ├── defaults.json         + db, stack, web sections; + tools.versions registry
│   └── schema.py             + DbConfig, StackConfig, WebConfig, VersionConstraint
└── tools/
    ├── (existing 11 tools unchanged)
    ├── db/                   ★ NEW
    │   ├── __init__.py
    │   ├── commands.py       Typer subapp dispatcher
    │   ├── manager.py        Shared engine-agnostic orchestration
    │   ├── models.py
    │   └── engines/
    │       ├── __init__.py
    │       ├── base.py       Abstract Engine (image, port, env, default-config)
    │       ├── mysql.py
    │       ├── mariadb.py
    │       ├── postgres.py
    │       ├── mongo.py
    │       └── phpmyadmin.py
    ├── stack/                ★ NEW
    │   ├── __init__.py
    │   ├── commands.py
    │   ├── manager.py        Multi-container compose-shaped orchestration
    │   └── lemp.py           LEMP recipe (nginx + php-fpm + db)
    ├── web/                  ★ NEW
    │   ├── __init__.py
    │   ├── nginx/
    │   │   ├── __init__.py
    │   │   ├── commands.py
    │   │   ├── manager.py
    │   │   └── templates.py  Hardened vhost templates (static, php, laravel)
    │   └── commands.py       `web` parent subapp dispatcher
    └── shell/
        └── colors.py         ★ NEW — palette-print subcommand for `shimkit shell colors`
```

Naming: tool packages use snake_case (`docker_clean`), Typer subapp
names use hyphens or single words (`docker-clean`, `db`, `stack`,
`web`). `web` is a parent app with one nested app (`nginx`) for now;
future siblings (`tls`, `caddy`, `apache`) slot in without rework.

## Cross-cutting: `core/docker.py`

The shimkit-flavored Docker SDK helper. Sits on top of
`docker` (the Python package; already pulled in by the `[docker-clean]`
extra, which the four new tools also gate on).

```python
class DockerEnv:
    """Builder + lifecycle for shimkit-managed containers.

    Owns the chokepoint to the docker SDK so per-tool managers
    don't reach for `docker.from_env()` directly. Boot-checks
    the daemon, surfaces clear EX_NOPERM (77) on docker-group
    issues, and EX_UNAVAILABLE (69) on missing daemon.
    """

    @classmethod
    def create(cls) -> DockerEnv: ...
    def boot(self) -> DockerEnv: ...         # verifies daemon reachable

    # ── conventions ────────────────────────────────────────
    @staticmethod
    def container_name(scope: str, kind: str, id_: str = "dev") -> str:
        """`shimkit-<scope>-<kind>-<id>`."""
        return f"shimkit-{scope}-{kind}-{id_}"

    @staticmethod
    def volume_path(engine: str, id_: str = "dev") -> Path:
        return Path.home() / ".shimkit" / "data" / "db" / f"{engine}-{id_}"

    # ── lifecycle (thin SDK wrappers via the existing pattern) ──
    def find(self, name: str): ...
    def run(self, image, *, name, env, ports, volumes, **kw): ...
    def stop(self, name): ...
    def remove(self, name, *, force=False): ...
    def exec(self, name, cmd: list[str], *, tty=False, capture=True): ...
    def logs(self, name, *, follow=False, tail=None): ...
```

Idempotency idiom: container name IS the marker. `up` becomes:

```
existing = env.find(name)
if existing and existing.status == "running":  return EX_OK  ("already up")
if existing and existing.status == "exited":   env.start(existing)
else:                                          env.run(image, name=name, ...)
```

No `~/.shimkit-engine-installed` files. The container's existence is
the proof.

## Cross-cutting: `core/version.py`

See [`version-constraints-spec.md`](./version-constraints-spec.md)
for the full spec. Surface summary:

```python
class ToolVersion:
    name: str
    version: packaging.version.Version | None
    raw: str

class VersionConstraint:
    min: str | None
    max: str | None
    preferred: str | None
    def check(self, v: packaging.version.Version) -> "Status": ...

class Status(Enum):
    OK           = "ok"
    OUT_OF_RANGE = "out_of_range"
    MISSING      = "missing"
    UNPARSEABLE  = "unparseable"

def detect(tool: str) -> ToolVersion | None: ...
def validate(tool: str, constraint: VersionConstraint) -> Result: ...
def validate_all() -> dict[str, Result]: ...           # used by `shimkit doctor`
```

Constraint declarations live in `config/defaults.json` under
`tools.versions.<name>`. Users override at
`~/.config/shimkit/shimkit.json` like any other config key. The same
constraint registry is consulted at three enforcement points:

1. **Install/setup time** — `pip install shimkit[docker-clean]` is a
   no-op for version constraints (we can't enforce at install time
   without writing `setup.py` install hooks, which is itself a smell).
   But the documented install pages can render the constraints from
   the config so users see them.
2. **Runtime preflight** — every `Manager.boot()` that depends on an
   external binary calls `version.validate(<tool>)`. Status:
   - `OK` → proceed silently
   - `OUT_OF_RANGE` → MODERATE warning, allow if `--force` (else
     exit 69)
   - `MISSING` → exit 69 (already existing pattern)
   - `UNPARSEABLE` → MODERATE warning, allow always (we don't want
     a vendor's version-string change to brick shimkit)
3. **`shimkit doctor`** — runs `validate_all()` and tabulates.

## Public CLI surface (v0.5.0)

Existing 11 tools unchanged. New:

```
shimkit db                            # menu
shimkit db ls                         # list shimkit-managed db containers
shimkit db <engine>                   # per-engine menu
shimkit db <engine> up [--port N] [--name id] [--bind 127.0.0.1|0.0.0.0] [--volume PATH | --ephemeral]
shimkit db <engine> down [--name id]
shimkit db <engine> shell [--name id]
shimkit db <engine> dump  [--name id] [--out PATH]
shimkit db <engine> reset [--name id]    # SEVERE — drops the volume
shimkit db <engine> status [--name id] [--json]
                                      # engines: mysql, mariadb, postgres, mongo, phpmyadmin

shimkit stack                         # menu
shimkit stack lemp up [--project name] [--db mysql|mariadb|postgres] [--port N]
shimkit stack lemp down [--project name]
shimkit stack lemp status [--project name]
shimkit stack lemp logs [--project name] [-f]
shimkit stack lemp exec <cmd...>      # `docker exec` inside the php-fpm container

shimkit web                           # menu
shimkit web nginx                     # menu
shimkit web nginx vhost generate --name <app> --domain <host> --root <path>
                                      # [--flavor static|php|laravel] [--out PATH]
shimkit web nginx vhost apply  --name <app>   # SEVERE — --confirm APPLY-VHOST
shimkit web nginx vhost remove --name <app>   # SEVERE — --confirm REMOVE-VHOST
shimkit web nginx vhost list

shimkit shell colors                  # 256-color palette diagnostic
```

## Confirmation tiers (unchanged model, applied to new tools)

| Tier | Examples in new tools |
|------|------------------------|
| NONE | `db <engine> status`, `db ls`, `stack lemp status`, `stack lemp logs`, `web nginx vhost list`, `web nginx vhost generate` (file-only), `shell colors` |
| MODERATE | `db <engine> up/down`, `stack lemp up/down`, `db <engine> dump` |
| SEVERE | `db <engine> reset` (`--confirm RESET-DB`), `web nginx vhost apply` (`--confirm APPLY-VHOST`), `web nginx vhost remove` (`--confirm REMOVE-VHOST`) |

Severe tokens are config-driven so users can rename them per-install.

## JSON config additions

Under `tools`:

```json
{
  "tools": {
    "db": {
      "default_volume_root": "~/.shimkit/data/db",
      "default_bind_host": "127.0.0.1",
      "default_id": "dev",
      "reset_severe_token": "RESET-DB",
      "engines": {
        "mysql":      {"image": "mysql:8.0",       "default_port": 13306},
        "mariadb":    {"image": "mariadb:10.11",   "default_port": 13307},
        "postgres":   {"image": "postgres:16",     "default_port": 15432},
        "mongo":      {"image": "mongo:7",         "default_port": 17017},
        "phpmyadmin": {"image": "phpmyadmin:5",    "default_port": 18080}
      }
    },
    "stack": {
      "default_project": "shimkit-dev",
      "lemp": {
        "nginx_image":   "nginx:1.27-alpine",
        "php_fpm_image": "php:8.3-fpm",
        "default_port":  18080,
        "default_db":    "mysql"
      }
    },
    "web": {
      "nginx": {
        "vhost_apply_severe_token": "APPLY-VHOST",
        "vhost_remove_severe_token": "REMOVE-VHOST",
        "sites_available_dir": "/etc/nginx/sites-available",
        "sites_enabled_dir":   "/etc/nginx/sites-enabled",
        "reload_cmd": ["nginx", "-s", "reload"]
      }
    },
    "versions": {
      "docker": {"min": "20.10",  "preferred": null, "max": null},
      "nginx":  {"min": "1.20",   "preferred": null, "max": null},
      "git":    {"min": "2.30",   "preferred": null, "max": null}
    }
  }
}
```

## Fluent API examples

```python
# Library use (rare; the CLI is the primary surface)
from shimkit.tools.db import DbManager

DbManager.create().boot().for_engine("mysql").up(
    port=13306, bind="127.0.0.1", volume=Path("~/sandbox/mysql"),
)

# Pre-flight a version constraint manually
from shimkit.core import version

result = version.validate("docker")
match result.status:
    case version.Status.OK:           ...
    case version.Status.OUT_OF_RANGE: ...
    case version.Status.MISSING:      ...
    case version.Status.UNPARSEABLE:  ...
```

## Extension pattern for adding more tools later

The new `db/engines/*.py` pattern is the **registry** the spec asks
for. Each engine is a class implementing `base.Engine`:

```python
class Engine(Protocol):
    name: str
    default_image: str
    default_port: int
    default_env: dict[str, str]                # for `docker run -e`
    def shell_cmd(self, *, name: str) -> list[str]: ...
    def dump_cmd(self, *, name: str) -> list[str]: ...
    def health_cmd(self) -> list[str] | None: ...   # docker HEALTHCHECK
```

Adding a Redis engine becomes a single file under `engines/`, a
config entry, and a registration line. Zero changes to the `db`
manager or commands.

Same registry idiom applies to `stack/<recipe>.py` (LEMP today; MERN
/ MEAN / Rails-stack tomorrow without touching the manager).

## What does NOT change

- Rule 1 (CommandRunner chokepoint) — `core/docker.py` does NOT
  call `docker` SDK behind the manager's back; it IS the manager-
  visible chokepoint, and SDK calls happen only inside it. Shimkit's
  rule-2 spirit (single subprocess pathway) extends to "single
  Docker-SDK pathway" via `core/docker.py`.
- Rule 2 (UI chokepoint) — every print still goes through `UI.*`.
- Rule 3 (config-driven values) — every new tool registers a config
  section; nothing is magic-stringed in code.
- Rule 4 (builder pattern) — `DockerEnv.create().boot()`,
  `DbManager.create().boot().for_engine("mysql")`,
  `StackManager.create().boot().lemp().up()`.
- Rule 5 (fluent self returns).
- Test layout: `tests/test_tools_db.py`, `tests/test_tools_stack.py`,
  `tests/test_tools_web.py`, `tests/test_core_version.py`,
  `tests/test_core_docker.py`. Docker is mocked at
  `core.docker.DockerEnv` boundary — no daemon access in tests.

## Backwards compatibility

None of the additions touch the existing 11 tools or their config
sections. The `[docker-clean]` extra is reused; its contents stay
the same. Anyone on shimkit v0.4.0 → v0.5.0 sees:

- 4 new top-level commands (`shimkit db`, `shimkit stack`, `shimkit web`, `shimkit shell colors`)
- 3 new optional config sections under `tools.{db,stack,web}` (all
  default-populated)
- `tools.versions` block — new but every entry is optional; absence
  means "no constraint".

No user-visible breaks.
