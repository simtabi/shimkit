# shimkit framework symfony

Symfony-specific helpers. Four commands today. Modelled on the
Laravel recipe — same parent sub-app, same builder pattern, same
host-or-container console passthrough — adjusted for Symfony's
conventions: writable `var/` (not `storage/`), `APP_SECRET` hex
(not `APP_KEY` base64), `bin/console` (not root `artisan`).

## Commands

| Command | Purpose |
|---------|---------|
| `shimkit framework symfony`                                  | Menu. |
| `shimkit framework symfony perms PATH [--group G]`           | MODERATE. Fix `var/` permissions. |
| `shimkit framework symfony env PATH [--name N] [--env E] [--db D]` | MODERATE. Scaffold `.env.local` with a generated `APP_SECRET`. |
| `shimkit framework symfony cache-clear PATH [--env E]`       | Wraps `php bin/console cache:clear --env <env>`. |
| `shimkit framework symfony console -- <args>`                | Passthrough to `bin/console` — host or LEMP container. |

Universal flags before the subcommand (`--quiet`, `--verbose`,
`--log-file`, `--no-color`, `--color`, `--no-input`); per-command
flags after (`--json`, `--dry-run`, `--yes`, `--force`).

## perms

`var/` is the standard Symfony writable tree (covers `cache/`,
`log/`, `sessions/`). Set `tools.framework.symfony.writable_dirs`
in your user config to extend (e.g. `["var", "public/uploads"]`).

```bash
# Default www-data group on Linux
shimkit framework symfony perms --yes ./my-symfony-app

# macOS-friendly group
shimkit framework symfony perms --yes --group staff ./my-symfony-app

# Dry-run plan
shimkit framework symfony perms --dry-run ./my-symfony-app

# JSON (CI / monitoring)
shimkit framework symfony perms --yes --json ./my-symfony-app
```

Group detection: `getent group <name>` on Linux, `dscl . -read
/Groups/<name>` on macOS, `grp.getgrnam()` Python fallback. When
the group doesn't exist on the host, the global `chmod 664` /
`chmod 775` passes still run but `chgrp` is skipped (UI.dim
explains).

## env

Writes `.env.local` with a freshly generated `APP_SECRET`. Symfony's
convention is that **`.env` (checked in) holds framework defaults**
and **`.env.local` (gitignored) holds secrets + per-host tweaks**.
shimkit writes to `.env.local` so the framework-provided `.env`
stays intact.

`APP_SECRET` is `secrets.token_hex(32)` = 64 hex chars — the
[Symfony reference](https://symfony.com/doc/current/reference/configuration/framework.html#secret)
recommends a long random hex.

`DATABASE_URL` defaults target the shimkit dev DBs:

| `--db`     | URL prefix | Port | `?serverVersion=` |
|------------|------------|-----:|-------------------|
| `mysql`    | `mysql://`     | 13306 | `8.0`         |
| `mariadb`  | `mysql://`     | 13307 | `mariadb-10.11` |
| `postgres` | `postgresql://`| 15432 | `16`          |

```bash
shimkit db postgres up
shimkit framework symfony env --yes --db postgres ./my-app
shimkit framework symfony console --project ./my-app -- doctrine:migrations:migrate
```

## cache-clear

Wraps `php bin/console cache:clear --env <env>`:

```bash
shimkit framework symfony cache-clear --env dev ./my-app
shimkit framework symfony cache-clear --env prod --in-container --stack myapp ./my-app
```

Default env is `dev` (configurable via
`tools.framework.symfony.default_env`).

## console

Generic passthrough to `bin/console`. Host execution is the
default — preflights `php` via `shimkit.core.version.preflight`,
exits 69 with the remediation hint when `php` is missing.
`--in-container` routes through `shimkit stack lemp`'s php-fpm
container.

```bash
# Host
shimkit framework symfony console --project ./my-app -- about
shimkit framework symfony console --project ./my-app -- doctrine:database:create

# Inside a running LEMP stack
shimkit stack lemp up --project myapp ./my-app
shimkit framework symfony console \
    --project ./my-app --in-container --stack myapp \
    -- doctrine:migrations:migrate
```

`--project` defaults to the current working directory.

## No cron-install

Symfony doesn't ship a built-in scheduler analogous to Laravel's
`schedule:run`. Application-specific cron entries can be installed
via `shimkit cron add` directly:

```bash
shimkit cron add --yes \
    --name my-symfony-nightly \
    --schedule "0 3 * * *" \
    --cmd "cd /var/www/my-app && php bin/console app:nightly-job >> /dev/null 2>&1"
```

If Symfony Scheduler (the messenger-based approach) gains broad
adoption, a `cron-install` command may land later.

## Configuration

```json
{
  "tools": {
    "framework": {
      "symfony": {
        "web_group": "www-data",
        "file_mode": "664",
        "dir_mode": "775",
        "writable_dirs": ["var"],
        "default_env": "dev"
      }
    }
  }
}
```

Override `web_group` per host. Add `writable_dirs` entries if your
app writes outside `var/` (e.g. `public/uploads/`).

## Exit codes

| Code | Meaning |
|-----:|---------|
| 0    | success |
| 1    | bad path, missing `bin/console`, refusing overwrite, prompt cancelled |
| 2    | Typer usage error |
| 69   | `EX_UNAVAILABLE` — wrong platform or missing `php` for `console`/`cache-clear` |
| 130  | SIGINT |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | full. Dev account typically owns the project, so `chgrp` is no-op'd unless `--group` is passed. |
| Linux    | full. Targets `www-data` by default; override with `--group`. |
| WSL      | works (Linux path). |
| Windows  | out of charter (use WSL). |
