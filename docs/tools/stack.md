# shimkit stack

Multi-container app recipes. One recipe today (`lemp`); the
registry pattern leaves room for `mern` / `rails` / `mean` as
single-file additions.

## shimkit stack lemp

Three containers per project, all attached to a per-project Docker
bridge network so they can talk by name:

| Role  | Default image       | Internal port |
|-------|---------------------|---------------|
| db    | `mysql:8.0` (configurable) | 3306 (or engine-default) |
| php   | `php:8.3-fpm`       | 9000 |
| nginx | `nginx:1.27-alpine` | 80 → 18080 on host |

Your project root (default: `$cwd`) is bind-mounted at `/srv/app`
inside both the php-fpm and nginx containers. The generated nginx
config does `fastcgi_pass` to the php container by name — no host
ports needed between them.

### Commands

| Command                                                          | Purpose                                            |
|------------------------------------------------------------------|----------------------------------------------------|
| `shimkit stack`                                                  | Menu.                                              |
| `shimkit stack ls`                                               | List every project's roles + status.               |
| `shimkit stack lemp up [--project N] [--db E] [--port P] [--project-root PATH] [--password PWD]` | Bring up 3 containers + network. MODERATE prompt. Idempotent. |
| `shimkit stack lemp down [--project N]`                          | Stop + remove all 3 + the network.                 |
| `shimkit stack lemp status [--project N] [--json]`               | Report each container's state.                     |
| `shimkit stack lemp logs [--project N] [--tail N] [-f]`          | Recent logs from each container.                   |
| `shimkit stack lemp exec [--project N] -- CMD...`                | Run a command in the php-fpm container.            |

### Naming convention

- network:  `shimkit-stack-lemp-<project>-net`
- db:       `shimkit-stack-lemp-<project>-db`
- php-fpm:  `shimkit-stack-lemp-<project>-php`
- nginx:    `shimkit-stack-lemp-<project>-nginx`

Default project is `shimkit-dev`. Use `--project myapp` to run
multiple stacks side-by-side; just give each a unique host port.

### Walkthrough

```bash
# 1. From inside your project's source directory
cd ~/code/my-laravel-app
shimkit stack lemp up --yes
# → http://127.0.0.1:18080

# 2. Run framework commands inside the container
shimkit stack lemp exec -- php artisan migrate
shimkit stack lemp exec -- composer install

# 3. Check what's up
shimkit stack lemp status

# 4. Tear it all down
shimkit stack lemp down --yes
```

### Side-by-side stacks

```bash
shimkit stack lemp up --yes --project alpha --port 18081 --project-root ~/code/alpha
shimkit stack lemp up --yes --project beta  --port 18082 --project-root ~/code/beta

shimkit stack ls
# shimkit stack (2 project(s))
#   alpha: db=running, nginx=running, php=running
#   beta:  db=running, nginx=running, php=running
```

Each project gets its own network, its own three containers, and
its own host port. No cross-talk between projects.

### Database engine choice

```bash
shimkit stack lemp up --yes --db mysql       # default
shimkit stack lemp up --yes --db mariadb
shimkit stack lemp up --yes --db postgres
```

The db container is launched with the **same engine drivers** as
`shimkit db` (W3) — same env-var conventions, same default port,
same image. The only difference is the container name: stack-owned
containers carry `shimkit-stack-lemp-<project>-db` rather than
`shimkit-db-<engine>-<id>`. If you also `shimkit db mysql up` in
parallel, they're entirely separate.

`mongo` and `phpmyadmin` aren't valid `--db` values for LEMP — that
acronym means SQL.

### Logs / exec

```bash
shimkit stack lemp logs                # last 100 lines per container
shimkit stack lemp logs --tail 500
shimkit stack lemp exec -- ls /srv/app # see the bind-mount from inside php-fpm
shimkit stack lemp exec -- env         # see container env
```

`exec` always targets the php-fpm container (where your app code
lives). For logs of a specific container, fall back to
`docker logs -f shimkit-stack-lemp-<project>-nginx` — multi-container
follow is intentionally not bundled here (it would need a
per-container thread or `docker logs --since now` polling).

### What `up` actually does

1. Creates a Docker user-defined bridge network if absent.
2. **db** container: image + env vars from the engine driver
   (W3's `engines/<name>.py`). Attached to the network. Not exposed
   on host.
3. **php-fpm** container: bind-mounts `<project_root>:/srv/app`.
   Attached to the network. Not exposed on host.
4. Renders an nginx conf to `/tmp/shimkit-stack-lemp-<project>-default.conf`
   that fastcgi-passes to the php container by name.
5. **nginx** container: bind-mounts `<project_root>:/srv/app` and
   the rendered conf to `/etc/nginx/conf.d/default.conf`. Attached
   to the network. Port 80 published on host's 127.0.0.1:18080.

`up` is idempotent — re-running with an already-up stack reports
`already_running` per role and does nothing. Stopped containers
get `docker start`-ed instead of recreated.

### JSON output

```bash
$ shimkit stack lemp up --yes --json --project-root .
{
  "ts": "...",
  "tool": "stack",
  "step": "lemp.up",
  "status": "ok",
  "data": {
    "project": "shimkit-dev",
    "db_engine": "mysql",
    "host_port": 18080,
    "project_root": "/path/to/cwd",
    "actions": {"db": "created", "php": "created", "nginx": "created"}
  }
}
```

### Configuration

```jsonc
{
  "tools": {
    "stack": {
      "default_project": "shimkit-dev",
      "lemp": {
        "nginx_image":   "nginx:1.27-alpine",
        "php_fpm_image": "php:8.3-fpm",
        "default_port":  18080,
        "default_db":    "mysql"
      }
    }
  }
}
```

Pin specific image tags (e.g. `php:8.2-fpm`) for project-specific
parity with prod.

### Adding a new recipe

`shimkit stack mern` doesn't exist yet. The registry pattern makes
it a single-file addition:

1. New `src/shimkit/tools/stack/mern.py` with `up/down/status/exec`
   functions mirroring `lemp.py`.
2. New typed `MernConfig` under `tools.stack.mern` in the schema.
3. Add a `mern_app` Typer subapp and register it in `commands.py`.

The shared `StackManager`, network helpers, and idempotent
container patterns are reused as-is.

## Exit codes

| Code | Meaning                                          |
|-----:|--------------------------------------------------|
| 0    | success / no-op                                  |
| 1    | unknown engine / exec non-zero / prompt cancel   |
| 2    | Typer usage error                                |
| 69   | EX_UNAVAILABLE — docker not on PATH, daemon down, or `tools.versions.docker` violated |
| 130  | SIGINT                                           |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | ✓ — Docker Desktop / Colima / OrbStack. Bind-mount perf can be a wart; consider Mutagen for hot files. |
| Linux    | ✓ — engine package + user in `docker` group |
| WSL      | ✓ — Docker Desktop's WSL integration |
| Windows  | ✗ — out of charter |

## Charter notes

`shimkit stack lemp` is the canonical example of the Docker-first
charter expansion (v0.5.0). The original ubuntu `install:lemp.sh`
was 5 lines of `sudo apt install ...` that left you with a
half-configured server. shimkit's version is a 3-container
isolated environment that comes up clean and tears down cleaner.
The host is not touched except for the bind-mount root and the
published port.
