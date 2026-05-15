# shimkit framework laravel

Laravel-specific helpers. Four commands today; future framework
recipes (Symfony, Rails, Django, Next.js) slot in under
`shimkit framework <name>` without disturbing the surface.

## Commands

| Command | Purpose |
|---------|---------|
| `shimkit framework laravel`                              | Menu. |
| `shimkit framework laravel perms PATH [--group G]`       | MODERATE. Fix storage + bootstrap/cache permissions. |
| `shimkit framework laravel env PATH [--name N] [--env E] [--db D]` | MODERATE. Scaffold a starter `.env` with a generated `APP_KEY`. |
| `shimkit framework laravel cron-install PATH [--name N] [--schedule S]` | MODERATE. Install a shimkit-managed cron entry for `php artisan schedule:run`. |
| `shimkit framework laravel artisan -- <args>`            | Passthrough to `php artisan`. Host by default; `--in-container` routes through `shimkit stack lemp`. |

Universal flags before the subcommand (`--quiet`, `--verbose`,
`--log-file`, `--no-color`, `--color`, `--no-input`); per-command
flags after (`--json`, `--dry-run`, `--yes`, `--force`).

## perms

Replaces the legacy `add:laravel-perms.sh` script. Runs:

- `chmod 664` on every file under the project tree.
- `chmod 775` on every directory.
- `chgrp -R <web_group> ug+rwx` on `storage/` and `bootstrap/cache/`,
  but **only** when the configured group exists on the host. On
  macOS dev workstations the group typically doesn't (the dev
  account owns the project), so the `chgrp` step is skipped and
  the global chmod still applies.

Group detection: `getent group <name>` on Linux, `dscl . -read
/Groups/<name>` on macOS, with a `grp.getgrnam()` Python fallback.
Override the default with `--group staff` (or any name on your host).

```bash
# Dry-run: print the chmod/chgrp plan without touching anything.
shimkit framework laravel perms --dry-run ./myshop

# Apply with the default www-data group.
shimkit framework laravel perms --yes ./myshop

# macOS-friendly group.
shimkit framework laravel perms --yes --group staff ./myshop

# JSON output (CI / monitoring).
shimkit framework laravel perms --yes --json ./myshop
```

## env

Writes a starter `.env` with a freshly generated `APP_KEY`.
**Refuses to overwrite an existing `.env`** — that file holds
production secrets in many setups, and shimkit doesn't clobber it.
If you want a clean reset, delete it manually first.

The generated `APP_KEY` is `base64:` plus 32 random bytes from
`secrets.token_bytes(32)`, base64-encoded — same shape Laravel
emits via `php artisan key:generate`. **`php` is not required on
the host** to scaffold a key.

Default DB settings point at the shimkit-managed dev databases
(see `shimkit db`):

| `--db`     | `DB_CONNECTION` | `DB_PORT` |
|------------|-----------------|----------:|
| `mysql`    | `mysql`         | `13306`   |
| `mariadb`  | `mysql`         | `13307`   |
| `postgres` | `pgsql`         | `15432`   |

So after `shimkit db mysql up` followed by `shimkit framework
laravel env --yes ./myshop`, the first `php artisan migrate` works
out of the box against the local container.

```bash
# Default: APP_NAME=<dirname>, APP_ENV=local, mysql on :13306
shimkit framework laravel env --yes ./myshop

# Custom name + staging environment + postgres on :15432
shimkit framework laravel env --yes \
    --name MyShop \
    --env staging \
    --db postgres \
    ./myshop
```

## cron-install

Wraps `shimkit cron add` with the Laravel-shaped invocation:

```
cd <PROJECT> && php <PROJECT>/artisan schedule:run >> /dev/null 2>&1
```

The default name is `laravel-<project-dirname>` and the default
schedule is `* * * * *` (every minute — Laravel's standard
scheduler pattern). Both can be overridden. Backup-on-mutate +
`shimkit cron rollback` come from the cron tool itself.

```bash
# Default: laravel-myshop @ * * * * *
shimkit framework laravel cron-install --yes ./myshop

# Custom name + 5-minute cadence
shimkit framework laravel cron-install --yes \
    --name myshop-scheduler \
    --schedule "*/5 * * * *" \
    ./myshop

# Preview without writing
shimkit framework laravel cron-install --dry-run ./myshop
```

`shimkit framework laravel cron-install` requires an `artisan`
file at the project root (refuses with exit 1 otherwise). If `php`
is not on `PATH`, the cron entry is still installed but a warning
explains the entry won't run until `php` is available.

## artisan

Passthrough to `php artisan`. Host execution is the default; pass
`--in-container` to route through the `shimkit stack lemp`
`php-fpm` container instead. Anything after the `--` is forwarded
verbatim, so `--seed`, `--force`, `--pretend` etc. all work.

```bash
# Host (requires php >= 8.1 on PATH)
shimkit framework laravel artisan --project ./myshop -- migrate
shimkit framework laravel artisan --project ./myshop -- key:generate

# Inside a running LEMP stack
shimkit stack lemp up --project myshop ./myshop
shimkit framework laravel artisan \
    --project ./myshop --in-container --stack myshop \
    -- migrate --seed
```

`--project` defaults to the current working directory.

## Configuration

```json
{
  "tools": {
    "framework": {
      "laravel": {
        "web_group": "www-data",
        "file_mode": "664",
        "dir_mode": "775",
        "writable_dirs": ["storage", "bootstrap/cache"],
        "default_cron_schedule": "* * * * *"
      }
    },
    "versions": {
      "php": {"min": "8.1"}
    }
  }
}
```

Change `web_group` to `staff` (macOS), `_www` (macOS legacy), or
your own group. `writable_dirs` is the list of directories that
get `chgrp` + `ug+rwx` applied — Laravel 9+ ships with
`storage/` and `bootstrap/cache/`; older projects with custom
writable trees can add entries.

`tools.versions.php` is the floor used by `shimkit framework
laravel artisan` (and `shimkit doctor`). Bump `min` to `8.2` or
`8.3` to enforce a higher version locally.

## Exit codes

| Code | Meaning |
|-----:|---------|
| 0    | success |
| 1    | bad path, missing `artisan`, refusing overwrite, prompt cancelled, sub-step failed |
| 2    | Typer usage error |
| 69   | `EX_UNAVAILABLE` — wrong platform or missing `php` for `artisan` |
| 130  | SIGINT |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | full. Dev account typically owns the project, so `chgrp` is no-op'd unless `--group` is passed. |
| Linux    | full. Targets `www-data` by default; override with `--group`. |
| WSL      | works (Linux path). |
| Windows  | out of charter (use WSL). |

## Charter notes

The legacy `add:laravel-perms.sh` and `add:cron.sh` scripts both
existed inside the ubuntu provisioning tree; the migration split
them into a generic primitive (`shimkit cron`) plus a Laravel
recipe layered on top (`shimkit framework laravel cron-install`).
Future framework helpers — `shimkit framework symfony`,
`shimkit framework rails`, etc. — fit into the same parent
sub-app.
