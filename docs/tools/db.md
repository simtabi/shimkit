# shimkit db

Container-first database orchestration. Six engines today
(`mysql`, `mariadb`, `postgres`, `mongo`, `redis`, `phpmyadmin`); every one
runs as a Docker container, bound to `127.0.0.1` by default,
backed by a host volume at `~/.shimkit/data/db/<engine>-<id>/`.

Skip the install-on-host path entirely. If you want
`mysql` running on your laptop, you `shimkit db mysql up`. Reset
the state with `shimkit db mysql reset --confirm RESET-DB`. Move
on. No apt-keys, no `/etc/mysql`, no `mysql_secure_installation`.

## Commands

| Command                                            | Purpose                                                              |
|----------------------------------------------------|----------------------------------------------------------------------|
| `shimkit db`                                       | Menu.                                                                |
| `shimkit db ls`                                    | List every `shimkit.tool=db` container.                              |
| `shimkit db <engine>`                              | Per-engine menu.                                                     |
| `shimkit db <engine> up`                           | Start a container (MODERATE prompt). Idempotent.                     |
| `shimkit db <engine> down`                         | Stop + remove (MODERATE prompt). Volume preserved.                   |
| `shimkit db <engine> shell`                        | Interactive client (`mysql` / `psql` / `mongosh` / ...).             |
| `shimkit db <engine> dump`                         | Stream a dump to stdout or `--out PATH`.                             |
| `shimkit db <engine> reset --confirm RESET-DB`     | **SEVERE.** Drop the container AND its volume.                       |
| `shimkit db <engine> status`                       | Inspect a single container.                                          |

Universal flags (before the subcommand): `--quiet`, `--verbose`,
`--log-file PATH`, `--no-color`, `--color`, `--no-input`.
Per-command flags (after the subcommand): `--json`, `--dry-run`,
`--yes`, `--force`, `--name <id>`, `--port N`, `--bind HOST`,
`--volume PATH`, `--ephemeral`, `--password PWD`, `--confirm TOKEN`,
`--on-host` (see below).

## --on-host (opt-out from container-first)

The default path is containers — that's how shimkit dissolves
the security flags from the original ubuntu provisioning scripts
(0.0.0.0 binds, deprecated apt-key, etc). If you've installed
mysql / mariadb / postgres on the host yourself (via apt, brew,
dnf), pass `--on-host` to manage *that* engine rather than a
container.

| `--on-host` command | What it does |
|---------------------|--------------|
| `shimkit db <engine> up --on-host`        | `systemctl start <service>` (Linux) / `brew services start <name>` (macOS). |
| `shimkit db <engine> down --on-host`      | `systemctl stop <service>` / `brew services stop <name>`. |
| `shimkit db <engine> status --on-host`    | Reports `running` / `stopped` / `missing`. |
| `shimkit db <engine> shell --on-host`     | `mysql -h 127.0.0.1 -uroot -p…` (or `psql`) directly against the host install. |

Limits:

- **mysql / mariadb / postgres only.** `mongo` and `phpmyadmin`
  reject `--on-host` (mongo's host packaging surface is messy
  and out of scope; phpmyadmin has no host install). Use the
  container path for those.
- **`shimkit` never installs the package.** If `mysql` (or
  `mariadb`, `psql`) isn't on PATH, the command refuses — install
  via your package manager first. This is deliberate: the
  install-on-host scripts in the original ubuntu source had
  five Critical security flags (0.0.0.0 binds, deprecated
  apt-key, curl|sh), and shimkit's redesign explicitly avoids
  reproducing them.
- Service names live in config (`tools.db.host_services.<engine>.{service_linux,service_macos}`).
  Override per-install if your distro or homebrew formula
  diverges from the defaults (e.g. `postgresql@16` on macOS,
  `postgresql` on Debian).

## Engines

| Engine | Image (default) | Host port | Container port | Admin user |
|--------|----------------|----------:|---------------:|------------|
| mysql      | `mysql:8.0`      | `:13306` | `3306`  | `root` |
| mariadb    | `mariadb:10.11`  | `:13307` | `3306`  | `root` |
| postgres   | `postgres:16`    | `:15432` | `5432`  | `postgres` |
| mongo      | `mongo:7`        | `:17017` | `27017` | `admin` |
| redis      | `redis:7-alpine` | `:16379` | `6379`  | n/a (`--requirepass`) |
| phpmyadmin | `phpmyadmin:5`   | `:18080` | `80`    | n/a (web UI) |

Shimkit-prefixed host ports keep a system-installed engine
(if any) from colliding. Override per-invocation with `--port` or
project-wide via `tools.db.engines.<engine>.default_port`.

### Redis (v0.15.0)

Redis is the odd engine: no admin user, no SQL, no dump. The
official `redis:7-alpine` image doesn't read a `REDIS_PASSWORD`
env var, so shimkit configures AUTH by passing `--requirepass`
as the container command. AOF persistence (`--appendonly yes`) is
on by default — that's the recommended dev posture.

- **`dump` is unsupported** — Redis backups are volume-level
  (the `/data/dump.rdb` file inside the managed volume), not
  logical dumps. Trigger one from the shell:
  `shimkit db redis shell` then `SAVE` (synchronous) or `BGSAVE`
  (background).
- **`--on-host` is unsupported** — same reason as mongo /
  phpmyadmin: shimkit doesn't install host packages. Users
  wanting host Redis run `brew install redis` /
  `apt install redis-server` themselves.

Default bind is **`127.0.0.1`** (loopback only). Override with
`--bind 0.0.0.0` if you really want to expose the port on the LAN —
and pair that with a sensible `--password`.

## up — examples

```bash
# The most common case
shimkit db mysql up --yes

# One LAN-reachable postgres with a strong password and a custom
# data dir
shimkit db postgres up --yes \
    --bind 0.0.0.0 --port 5432 \
    --password 'change-me-now' \
    --volume /srv/projects/foo/db

# Two parallel mongo containers
shimkit db mongo up --yes --name dev
shimkit db mongo up --yes --name qa  --port 17018

# Ephemeral (data lost on `down`)
shimkit db postgres up --yes --ephemeral

# Look before you leap
shimkit db mysql up --yes --dry-run
shimkit db mysql up --yes --json
```

`up` is idempotent. Re-running with an already-running container is
a no-op. An existing-but-stopped container gets `docker start`-ed
instead of recreated. A fresh `up` calls `docker run` and creates the
volume dir at the conventional path.

## shell — examples

```bash
shimkit db mysql shell
shimkit db postgres shell
shimkit db mongo shell

# Interactive — your terminal goes into the client's REPL.
```

Each engine's shell uses its native client (`mysql` / `psql` /
`mongosh`). The `docker exec -it` wrapper hands the TTY to the user,
so paging / history / readline all work.

## dump — examples

```bash
# Stream to stdout
shimkit db mysql dump | gzip > backup-$(date +%F).sql.gz

# Or directly to a file
shimkit db postgres dump --out backup.sql

# Mongo's dump is binary (BSON archive)
shimkit db mongo dump --out backup.archive
```

Per-engine commands used inside the container:

- `mysql` → `mysqldump --all-databases --single-transaction --quick`
- `mariadb` → `mariadb-dump --all-databases --single-transaction`
- `postgres` → `pg_dumpall --clean`
- `mongo` → `mongodump --archive --quiet` (binary)
- `phpmyadmin` → not supported

## phpmyadmin

phpMyAdmin is a web UI, not a database. Bring it up alongside a
backing database that's also a shimkit container; the UI connects via
the host's published port using Docker's `host.docker.internal`
bridge (added to `/etc/hosts` inside the container via
`extra_hosts={"host.docker.internal": "host-gateway"}` so it works on
Linux too).

```bash
shimkit db mysql up --yes                              # bring up the DB first
shimkit db phpmyadmin up --yes --link-port 13306       # → http://localhost:18080
```

`--link-host` overrides `host.docker.internal` if you want phpMyAdmin
to connect to a non-shimkit DB instead. `--link-port` defaults to
`13306` (shimkit's mysql port).

phpMyAdmin doesn't have `shell` / `dump` / `reset` paths — only `up`
/ `down` / `status`. Its container is stateless (sessions live in
memory).

## reset — SEVERE

```bash
shimkit db mysql reset --confirm RESET-DB
shimkit db mysql reset --dry-run             # confirm not required
```

Drops the container with `--force` AND deletes the host volume.
There is no rollback. The SEVERE token (`RESET-DB` by default;
configurable as `tools.db.reset_severe_token`) guards against an
accidental `Tab`-completed `reset`. `remove_volume()` is itself
defended — it refuses any path that isn't under
`~/.shimkit/data/`.

## ls — multi-engine view

```bash
shimkit db ls
shimkit db ls --json
```

Lists every container with the `shimkit.tool=db` label, regardless
of engine. Useful when you've got several DBs going for different
projects.

## JSON output

Every command supports `--json`. `up` shape:

```json
{
  "ts": "...",
  "tool": "db",
  "step": "up",
  "status": "ok",
  "data": {
    "engine": "mysql",
    "container_name": "shimkit-db-mysql-dev",
    "image": "mysql:8.0",
    "host_port": 13306,
    "container_port": 3306,
    "bind_host": "127.0.0.1",
    "action": "created",
    "volume_path": "/Users/you/.shimkit/data/db/mysql-dev"
  }
}
```

`action` is one of `"created"`, `"started"` (existed stopped), or
`"already_running"`.

## Configuration

```jsonc
{
  "tools": {
    "db": {
      "default_volume_root": "~/.shimkit/data/db",
      "default_bind_host": "127.0.0.1",
      "default_id": "dev",
      "default_password": "shimkit-dev",
      "reset_severe_token": "RESET-DB",
      "engines": {
        "mysql":      {"image": "mysql:8.0",     "default_port": 13306},
        "mariadb":    {"image": "mariadb:10.11", "default_port": 13307},
        "postgres":   {"image": "postgres:16",   "default_port": 15432},
        "mongo":      {"image": "mongo:7",       "default_port": 17017},
        "phpmyadmin": {"image": "phpmyadmin:5",  "default_port": 18080}
      }
    }
  }
}
```

Pin a specific image tag in `engines.<engine>.image` if you need a
matching prod version.

## Adding a new engine

`shimkit db redis up` doesn't exist yet, but the registry pattern
makes it a single-file addition:

1. New `src/shimkit/tools/db/engines/redis.py` with a class
   `Redis(Engine)`.
2. Register in `engines/__init__.py::REGISTRY`.
3. Default image + port in `config/defaults.json::tools.db.engines.redis`.

No changes to the manager, the commands layer, or the test scaffolding.

## Exit codes

| Code | Meaning                                                |
|-----:|--------------------------------------------------------|
| 0    | success / no-op                                        |
| 1    | unknown engine / missing container / unsupported op / SEVERE token missing |
| 2    | Typer usage error                                      |
| 69   | EX_UNAVAILABLE — docker not on PATH, daemon unreachable, or `tools.versions.docker` violated |
| 130  | SIGINT                                                 |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | ✓ — Docker Desktop / Colima / OrbStack |
| Linux    | ✓ — engine package + user in `docker` group |
| WSL      | ✓ — Docker Desktop's WSL integration or native Linux Docker |
| Windows  | ✗ — out of charter |

## Charter notes

`shimkit db` is the **first** server-class tool to ship under the
Docker-first charter expansion (Phase 3 of the v0.5.0 migration
plan). There is no `--on-host` path; if you want the apt-installed
version of mysql on your laptop, you install it the way you've
always installed it. shimkit's value here is the *container*
lifecycle, not the package manager.
