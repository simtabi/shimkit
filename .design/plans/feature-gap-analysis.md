# Feature gap analysis — `ubuntu/` → `shimkit`

> Phase 2 deliverable. Bias is **skip-by-default**; **adopt** only
> when the feature is differentiated, safe, and aligns with the
> charter. **Docker-first** for server-class work; host-mutation is
> opt-in.

## Feature matrix

Columns:

- **Source** — file path under `ubuntu/scripts/initializers/scripts/`
- **Purpose** — one-line
- **Has shimkit?** — Y / N / partial
- **Quality of existing** — n/a / good / ok / poor (where Y or partial)
- **Recommendation** — adopt / improve / skip / defer
- **Risk** — see `.design/plans/_workspace/risk-flags.md` (C-prefix
  = Critical, H = High, M = Medium, L = Low)
- **Effort** — S (~150 LOC) / M (~300 LOC) / L (~500 LOC) post-redesign

### Installers — `installers/`

| Source | Purpose | Has shimkit? | Quality | Recommendation | Risk | Effort |
|---|---|---|---|---|---|---|
| `database/install:maria.sh` | MariaDB host install | N | n/a | **adopt** as Docker — `shimkit db mariadb up/down/shell` | C1, H2, H3, C4 in source → resolved by container | M (shared with mysql) |
| `database/install:mysql.sh` | MySQL host install | N | n/a | **adopt** as Docker — `shimkit db mysql up/down/shell` | C3, H1, H7 → resolved | M |
| `database/install:mongo.sh` | MongoDB host install | N | n/a | **adopt** as Docker — `shimkit db mongo up/down/shell` | C2, C4, M7 → resolved | M |
| `database/install:postgres.sh` | Postgres host install | N | n/a | **adopt** as Docker — `shimkit db postgres up/down/shell` | none material | M |
| `stacks/install:lemp.sh` | LEMP one-shot orchestrator | N | n/a | **adopt** as Docker compose — `shimkit stack lemp up/down/status` | inherits db risks → resolved | L |
| `tools/install:certbot.sh` | Certbot host install | N | n/a | **defer** — TLS issuance is non-trivial; needs DNS-01 design for container mode | H4 | L (when picked up) |
| `tools/install:composer.sh` | PHP composer host install | N | n/a | **skip** — covered by the `php:` container in `shimkit stack lemp`; users wanting host-side composer have `brew install composer` / `apt install composer` | none | — |
| `tools/install:node.sh` | NodeJS LTS host install | N | n/a | **skip** — `nvm` / `volta` / `asdf` are the industry standard; shimkit shouldn't compete | C5 | — |
| `tools/install:packages.sh` | Bulk apt utility-package install | N | n/a | **skip** — out of charter; the per-tool model is the antithesis of "bulk apt" | none | — |
| `tools/install:php.sh` | PHP 8.2 host install | partial (broken — installPHPPackages never called) | poor | **skip** — host PHP install is `shimkit stack lemp`'s job inside a container; users wanting host PHP have `brew install php` / phpbrew | M2 | — |
| `tools/install:php7.sh` | PHP host install (misnamed; installs 8.0) | partial (broken — literal `apt install -packages/extentions-`) | broken | **skip** — same as above, also broken | M1 | — |
| `tools/install:phpmyadmin.sh` | phpMyAdmin host install + nginx ln | N | n/a | **adopt** as Docker — `shimkit db phpmyadmin up/down` (linked to a mysql/mariadb container by name) | H6 → resolved (container has no shell, no default exposed port) | S |
| `tools/install:server-env.sh` | "server env" (apt install nginx) | N | n/a | **skip** — near-duplicate of `install:nginx.sh`; nginx covered via `shimkit stack lemp` and `shimkit web nginx` | M3 | — |

### Configurators — `configurators/`

| Source | Purpose | Has shimkit? | Quality | Recommendation | Risk | Effort |
|---|---|---|---|---|---|---|
| `alliases/aliases` | Bash aliases (`art=artisan`, php version switch, `xon`/`xoff`, etc.) | N | n/a | **skip** — alias curation is per-user dotfile territory, not packagable | L1 | — |
| `configs/configs:supervisor.sh` | Supervisor program-block generator | N | n/a | **skip** — supervisor is fading (container restart policies / systemd cover this); too Laravel-shaped | none | — |
| `crons/add:cron.sh` | Laravel scheduler cron entry | N | n/a | **defer** — generic `shimkit cron add/list/remove` is appealing but Laravel-specific shape here isn't | M4 | M (when picked up) |
| `database/create:mysql.sh` | `CREATE DATABASE` wrapper | N | n/a | **skip** — subsumed by `shimkit db mysql shell` + plain SQL | none | — |
| `servers/nginx:host.sh` | Generic nginx vhost generator | N | n/a | **adopt** — `shimkit web nginx vhost generate` (file-only by default, `--apply` for install + reload). Modernise socket path (PHP version detected via `php -v` or config) | H5 | M |
| `servers/nginx:laravel.sh` | Laravel-flavored vhost | N | n/a | **fold-in** to above as `--flavor laravel` (sets `root=$path/public`) | H5 | (covered by above) |
| `tools/expressjs:setup.sh` | Express + systemd unit | N | n/a | **skip** — too project-shaped; users wanting this run `npm init` themselves | none | — |
| `tools/laravel:file-perms.sh` | Laravel storage perms fixer | N | n/a | **defer** — niche Laravel-specific; could go in a future `shimkit framework laravel` tool. Skip for now | M5, M6 | S (when picked up) |
| `tools/laravel:initialize.sh` | Clone repo + composer install + .env + migrate | N | n/a | **skip** — too project-shaped; that's a `make`/Taskfile concern | none | — |

### Assets — `assets/`

| Source | Purpose | Has shimkit? | Quality | Recommendation | Risk | Effort |
|---|---|---|---|---|---|---|
| `assets/bash-colors.sh` | ANSI palette printer + PS1-with-git-branch helpers | partial — `core/ui.py` has ANSI constants but no palette display | ok | **adopt the palette-display piece** as `shimkit shell colors` (read-only diagnostic). Skip the PS1 helpers — that's dotfiles. | none | S |
| `assets/bash-colors.md` | Author notes / usage of the above | N | n/a | **fold-in** to `docs/tools/shell.md` colors section | none | (covered) |

### Other

| Source | Purpose | Recommendation |
|---|---|---|
| `__src/server-main/`, `__src/server-main 2/` | Legacy flat layout | **skip** (archive only) |
| `scripts/initializers/server-main/` | Empty installer scaffold | **skip** (archive only) |
| `scripts/security/`, `docs/`, `scripts/help.sh` | Empty | **skip** |

---

## Adopt list (must-have for v0.5.0)

Grouped under three new top-level sub-apps. Existing 11 tools stay flat.

### `shimkit db <name>` — single-container databases

Each subcommand is a thin wrapper around `docker run` / `docker
exec` / `docker stop` of the upstream official image. The image
tag is configurable; defaults bias toward LTS / latest-stable. No
host install option (skip-by-design — these are servers, not CLI
tools, and the modern way to "have postgres on your laptop" is to
have a postgres container).

```
shimkit db
shimkit db ls                              # list shimkit-managed db containers
shimkit db mysql up [--port 3306] [--name <id>] [--volume <path>]
shimkit db mysql down [--name <id>]
shimkit db mysql shell [--name <id>]       # interactive mysql client
shimkit db mysql dump [--name <id>] > out.sql
shimkit db mariadb up/down/shell/dump
shimkit db postgres up/down/shell/dump
shimkit db mongo up/down/shell/dump
shimkit db phpmyadmin up [--link <db-name>] [--port 8080]
shimkit db phpmyadmin down
```

Conventions per container:

- Container name `shimkit-db-<engine>-<id>` (default id `dev`).
- Default password (configurable) only ever bound to `127.0.0.1`
  unless the user passes `--bind 0.0.0.0` (MODERATE prompt).
- Persistent volume at `~/.shimkit/data/db/<engine>-<id>/` by
  default. `--volume PATH` overrides; `--ephemeral` skips the mount.
- `--json` emits the docker-inspect-shaped state for scripting.

### `shimkit stack <name>` — multi-container stacks

Composes the `db` primitives plus an `nginx` + `php-fpm` set.
Internally builds a temporary docker-compose-shaped state. No
`docker-compose` binary requirement — we drive the Docker SDK
directly.

```
shimkit stack
shimkit stack ls
shimkit stack lemp up [--port 8080] [--project <name>] [--db mysql|mariadb|postgres]
shimkit stack lemp down [--project <name>]
shimkit stack lemp status [--project <name>]
shimkit stack lemp logs [--project <name>] [-f]
shimkit stack lemp exec <cmd...>           # exec inside the php-fpm container
```

LEMP = nginx + php-fpm + mysql (or whichever db the user picks).
Bind-mounts cwd at `/srv/app` inside the php-fpm container by
default.

### `shimkit web nginx` — nginx vhost generator (host- and container-mutating)

Generates RFC-style hardened nginx vhost files. Default mode:
**file-only** — writes to a path you pass with `--out PATH` and
never touches `/etc/nginx/`. Opt-in `--apply` mode mutates
`/etc/nginx/sites-{available,enabled}/` and reloads nginx with the
SEVERE token.

```
shimkit web nginx
shimkit web nginx vhost generate \
  --name <app> --domain <host> --root <path> [--flavor static|laravel|php] \
  [--out /tmp/vhost.conf]
shimkit web nginx vhost apply --name <app>      # SEVERE — needs --confirm APPLY-VHOST
shimkit web nginx vhost remove --name <app>     # SEVERE
shimkit web nginx vhost list                    # what's installed at /etc/nginx/sites-enabled
```

### `shimkit shell colors` — palette diagnostic

```
shimkit shell colors                     # print 256-color palette
shimkit shell colors --json              # the same as a structured dump
```

Read-only. Useful for debugging "my new terminal theme broke the
shimkit help output".

---

## Skip list (with one-line reason each)

| Source | Reason |
|---|---|
| `install:certbot.sh` | TLS issuance design is non-trivial under the Docker charter (DNS-01 vs HTTP-01); defer to v0.6+ |
| `install:composer.sh` | Composer ships inside the LEMP php container; host install belongs to `brew` / `apt` |
| `install:node.sh` | `nvm` / `volta` / `asdf` are the industry standard; competing is a charter overreach |
| `install:packages.sh` | Bulk apt installer is the antithesis of shimkit's per-tool design |
| `install:php.sh` | Host PHP install is `shimkit stack lemp`'s job; users wanting host PHP have `brew install php` |
| `install:php7.sh` | Broken (`apt install -packages/extentions-`); also obsolete name (installs PHP 8.0) |
| `install:server-env.sh` | Near-duplicate of an nginx installer; both redundant with `shimkit stack lemp` |
| `configurators/aliases` | Alias curation is per-user dotfile territory |
| `configs:supervisor.sh` | Supervisor is fading vs. container restart policies / systemd |
| `add:cron.sh` | Laravel-specific shape; a generic `shimkit cron` is a v0.6+ candidate |
| `create:mysql.sh` | Subsumed by `shimkit db mysql shell` + SQL |
| `expressjs:setup.sh` | Too project-shaped (clones a git repo, writes a systemd unit); not packagable |
| `laravel:initialize.sh` | Too project-shaped; that's a `make` / Taskfile concern |
| `laravel:file-perms.sh` | Niche Laravel-only; defer to a future `shimkit framework laravel` tool |
| `__src/server-main/`, `__src/server-main 2/`, `scripts/initializers/server-main/`, `scripts/security/`, `docs/`, `scripts/help.sh` | Empty / duplicate / legacy |
| `assets/bash-colors.sh` (PS1 helpers) | Dotfile territory; only the palette printer ports cleanly |

---

## Improvement list

Places where the source has a pattern shimkit could borrow:

| Source pattern | Where it could help shimkit |
|---|---|
| Marker file for idempotency (`~/.maria`) | Reframed as "container-name-is-the-marker": `docker inspect <name>` either succeeds → already up, or fails → fresh start. shimkit's existing `Manager.boot()` pattern is similar but doesn't bake in this idiom — could be a `core/docker.py` helper. |
| `debconf-set-selections` for non-interactive DB install | N/A in container mode (image baked with the right state) but it's the technique behind unattended host installs if `--on-host` is ever wired |
| Security-hardened nginx vhost template (X-Frame-Options, X-XSS-Protection, server_tokens off, Referrer-Policy) | Adopt verbatim into `shimkit web nginx vhost`'s template, plus modern additions (Content-Security-Policy, Permissions-Policy, HSTS when TLS) |
| Laravel-shaped vhost (`root=$path/public`, `index.php` fallback) | Adopt as `--flavor laravel` |

---

## Effort total (Adopt list only)

| Item | Effort |
|---|---|
| `shimkit db` (mysql, mariadb, postgres, mongo, phpmyadmin — shared driver) | L (~600 LOC + 60 tests) |
| `shimkit stack lemp` (composes the above + nginx + php-fpm container) | M (~350 LOC + 30 tests) |
| `shimkit web nginx vhost` (generate file + apply gated) | M (~300 LOC + 25 tests) |
| `shimkit shell colors` | S (~80 LOC + 8 tests) |
| **Total** | ≈ 1,330 LOC, 123 tests over current 351 → 474 tests floor |

---

## Decisions deferred to v0.5.x+

- `shimkit tls / certbot` — TLS issuance under Docker charter.
- `shimkit cron add/list/remove` — generic cron-managed-by-shimkit.
- `shimkit framework laravel` — Laravel-specific tooling (`laravel:file-perms`, the .env generator from `laravel:initialize`).
- `shimkit on-host` mode for `db` / `stack` — explicit `--on-host` paths that re-implement the apt-install paths SAFELY (with apparmor preserved, with bind-address sane, with deprecated `apt-key` replaced by `signed-by`). Probably v0.6+.

---

## Open questions for the maintainer (Phase 3 input)

1. **Naming**: `shimkit db mysql` vs `shimkit database mysql` vs `shimkit data mysql`? Spec says "grouped well". I lean `db` (short, terminal-friendly).
2. **Default ports**: should `shimkit db mysql up` default to `:3306` on host (collides with system mysql), `:13306` (clearly shimkit), or random? Lean `:13306`.
3. **Volume location**: `~/.shimkit/data/db/<engine>/` (under home) vs `~/Library/Application Support/shimkit/db/<engine>/` on mac / XDG on linux? Lean simple `~/.shimkit/data/`.
4. **Docker SDK extra**: `[docker-clean]` already pulls `docker>=7.1`. New `[server]` extra for the new sub-apps, or reuse `[docker-clean]`? Lean **new `[server]` extra** so users who only want `docker-clean` don't pay for the rest.
5. **`shimkit web nginx` blast radius**: file-only-by-default (`--apply` is opt-in) seems right. Confirm. Apply mode should require either `--confirm APPLY-VHOST` OR a passed-config path so we know the user means it.
