# Source inventory — `/Users/imanimanyara/Artisan/projects/opensource/simtabi/ubuntu/`

> **Workspace document.** Scratch space for Phase 1; not referenced
> by code or shipped docs. Will be cleaned at validation.

Snapshot taken 2026-05-15. Source is **not in any git repository** —
no recovery exists outside the working tree. Total: 88 tracked files
(excluding `.DS_Store`), ~416 KB. mtimes cluster around 2022-09-28
(legacy) and 2024-2025 (curated rewrite).

## Top-level shape

```
ubuntu/
├── __src/                         # legacy — pre-restructure
│   ├── server-main/               # 25 files
│   └── server-main 2/             # 31 files — duplicate of server-main
│                                  #   with .idea/ added (Finder/IDE copy)
├── scripts/
│   ├── help.sh                    # empty stub
│   ├── initializers/
│   │   ├── initialize.sh          # JREAM-branded TUI menu (Ubuntu 22.04)
│   │   ├── scripts/
│   │   │   ├── configurators/     # POST-INSTALL configuration
│   │   │   │   ├── alliases/      # (sic — typo)
│   │   │   │   │   └── aliases    # bash aliases + php-version helpers
│   │   │   │   ├── configs/
│   │   │   │   │   └── configs:supervisor.sh
│   │   │   │   ├── crons/
│   │   │   │   │   └── add:cron.sh
│   │   │   │   ├── database/
│   │   │   │   │   └── create:mysql.sh
│   │   │   │   ├── servers/
│   │   │   │   │   ├── nginx:host.sh        # generic vhost generator
│   │   │   │   │   └── nginx:laravel.sh     # Laravel-shaped vhost
│   │   │   │   └── tools/
│   │   │   │       ├── expressjs:setup.sh
│   │   │   │       ├── laravel:file-perms.sh
│   │   │   │       └── laravel:initialize.sh
│   │   │   └── installers/        # PACKAGE INSTALL on a fresh server
│   │   │       ├── database/
│   │   │       │   ├── install:maria.sh
│   │   │       │   ├── install:mongo.sh
│   │   │       │   ├── install:mysql.sh
│   │   │       │   └── install:postgres.sh
│   │   │       ├── stacks/
│   │   │       │   └── install:lemp.sh
│   │   │       └── tools/
│   │   │           ├── install:certbot.sh
│   │   │           ├── install:composer.sh
│   │   │           ├── install:node.sh
│   │   │           ├── install:packages.sh
│   │   │           ├── install:php.sh
│   │   │           ├── install:php7.sh
│   │   │           ├── install:phpmyadmin.sh
│   │   │           └── install:server-env.sh
│   │   └── server-main/           # 5 files; newer-than-__src/server-main
│   │                              # README + index.sh + installer.sh + help.sh + test.sh
│   └── security/                  # EMPTY DIR
├── assets/
│   ├── bash-colors.md
│   └── bash-colors.sh             # palette printer + PS1 helpers
└── docs/                          # EMPTY DIR
```

## Duplicate / superseded subtrees

| Tree                              | Status                          | Action |
|-----------------------------------|---------------------------------|--------|
| `__src/server-main/`              | Legacy flat layout              | SKIP (canonical version lives under `scripts/initializers/scripts/`) |
| `__src/server-main 2/`            | Finder copy + IDE config        | SKIP (identical to above + `.idea/`) |
| `scripts/initializers/server-main/` | Newer driver scaffold; 5 files | SKIP for now (`installer.sh` is just an alias-installer; not the actual feature surface) |
| `scripts/security/`               | Empty directory                 | SKIP |
| `docs/`                           | Empty directory                 | SKIP |
| `scripts/help.sh`                 | Empty file                      | SKIP |

**Canonical feature surface for the migration**:
`scripts/initializers/scripts/{installers,configurators}/`. 22 actual
scripts. Plus `assets/bash-colors.{md,sh}` and the `aliases` file.

## File classification (canonical surface only)

| Class           | Count | Notes |
|-----------------|------:|-------|
| Installers (shell) | 13 | apt + add-apt-repository wrappers; mutating |
| Configurators (shell) | 8 | vhost generators, cron, supervisor, perms |
| Bash assets | 2 | palette printer + aliases |
| Docs (md) | 3 | bash-colors.md + 2 READMEs (one per server-main tree) |

## Feature-level enumeration (canonical surface)

### Installers (host-mutating apt-based)

| File | Installs | Notable patterns |
|------|----------|------------------|
| `installers/database/install:maria.sh` | MariaDB 10.2 | Marker `/home/vagrant/.maria` (Homestead origin); `apt-key adv` (deprecated); `rm -rf /var/lib/mysql`; **disables apparmor** (security regression); takes `$1 $2 $3` for root/user/password |
| `installers/database/install:mongo.sh` | MongoDB 3.4 | Marker `/home/capybara/.mongo`; `apt-key adv` deprecated; **`bindIp 0.0.0.0`** (publicly listens); opens UFW 27017 |
| `installers/database/install:mysql.sh` | MySQL | Reads password via stdin then **passes plaintext on the command line** to `mysql --user= --password=`; grants `*.*` to `'%'`; binds to `*` |
| `installers/database/install:postgres.sh` | Postgres | Minimal: `apt install postgresql postgresql-contrib` |
| `installers/stacks/install:lemp.sh` | LEMP | Orchestrator: calls 5 other installers sequentially |
| `installers/tools/install:certbot.sh` | Certbot | `add-apt-repository ppa:certbot/certbot` (deprecated PPA) |
| `installers/tools/install:composer.sh` | Composer | Uses `apt install composer` AND the upstream installer with sig verification (mixed; good sig check) |
| `installers/tools/install:node.sh` | Node LTS | `curl …\| sudo -E bash -` (RISK) |
| `installers/tools/install:packages.sh` | Bulk packages | curl, fail2ban, nmap, ufw, vim, zsh, etc — meta-installer |
| `installers/tools/install:php.sh` | PHP 8.2 | Mixed Apache+nginx module list; never executed (`installPHPPackages` defined but not called) |
| `installers/tools/install:php7.sh` | PHP 8.0 (misnamed) | Adds `ondrej/php` PPA; broken: `apt install -packages/extentions-` |
| `installers/tools/install:phpmyadmin.sh` | phpMyAdmin | Hardcoded `php8.0-fpm` socket reference |
| `installers/tools/install:server-env.sh` | Server env | Duplicates `install:nginx.sh`; defines unused package lists |

### Configurators (post-install, mostly interactive `read`)

| File | Configures | Notable patterns |
|------|------------|------------------|
| `configurators/configs/configs:supervisor.sh` | supervisor program block | Interactive `read`-based menu; writes per-program `.conf` |
| `configurators/crons/add:cron.sh` | root crontab entry | Touches `/var/spool/cron/root`; hardcoded `php $path/artisan schedule:run` (Laravel-specific) |
| `configurators/database/create:mysql.sh` | mysql `CREATE DATABASE` | Wraps the mysql CLI; password via `-p` prompt |
| `configurators/servers/nginx:host.sh` | generic nginx vhost | Heredoc with security headers; hardcoded `php8.0-fpm` socket |
| `configurators/servers/nginx:laravel.sh` | Laravel vhost | Same shape as `nginx:host.sh` but root → `$path/public` |
| `configurators/tools/expressjs:setup.sh` | Express.js + systemd | Clones repo, writes systemd unit, enables it |
| `configurators/tools/laravel:file-perms.sh` | Laravel storage/bootstrap perms | `chgrp www-data`, ACLs, `php artisan storage:link --force` |
| `configurators/tools/laravel:initialize.sh` | Laravel project bootstrap | Heavy `read` interactive flow; composer install, .env, artisan key:generate, migrate |

### Assets

| File | Use |
|------|-----|
| `assets/bash-colors.sh` | Palette printer + PS1-with-git-branch helpers; ANSI sequence constants |
| `assets/bash-colors.md` | Author/usage notes |
| `configurators/alliases/aliases` | bash aliases (`art=artisan`, `xoff`, `xon`, `php56..php72` version-switching, `serve-apache`, `dusk`) |

## Patterns observed

1. **Interactive `read`-prompts everywhere** — no `--yes`, `--no-input`,
   `--json`. Not scriptable from shimkit's own non-interactive style.
2. **Idempotency via marker files** — `~/.maria`, `~/.mongo`. Implies
   Homestead/Vagrant origin (`/home/vagrant`, `/home/capybara`).
3. **Hardcoded PHP-FPM socket paths** that DON'T match the version
   being installed (e.g. install PHP 8.2, vhost expects `php8.0-fpm`).
4. **`apt-key adv` for repo trust** — deprecated since Ubuntu 22.04.
5. **`sudo` everywhere** — these scripts assume root + a fresh server.
6. **No idempotency** for most configurators — re-running re-creates,
   re-prompts, sometimes appends duplicates (cron entries, vhost
   files).
7. **Several broken scripts** — `install:php7.sh` line 6
   (`apt install -packages/extentions- -y` is malformed),
   `install:php.sh` defines `installPHPPackages` but never calls it,
   `install:server-env.sh` near-duplicate of `install:nginx.sh`.
8. **Output rendered via plain `echo`** — bash-colors.sh has a
   pleasant palette but the scripts themselves don't use it.

## SHA-256 manifest

Full manifest at `/tmp/ubuntu-inventory.tsv` (will move into the
archive at Phase 7). 88 lines; first 12 chars of each SHA + size +
mtime + relative path.
