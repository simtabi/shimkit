# shimkit framework django

Django-specific helpers. Third recipe under the `framework`
parent. Same shape as the Laravel + Symfony recipes; adjusted
for Django's conventions.

## Commands

| Command | Purpose |
|---------|---------|
| `shimkit framework django`                                  | Menu. |
| `shimkit framework django perms PATH [--group G]`           | MODERATE. Fix `media/` + `staticfiles/` permissions. |
| `shimkit framework django env PATH [--name N] [--debug/--no-debug] [--db D]` | MODERATE. Scaffold `.env` with `SECRET_KEY` + `DATABASE_URL`. |
| `shimkit framework django migrate PATH`                     | Wraps `python manage.py migrate --no-input`. |
| `shimkit framework django manage -- <args>`                 | Passthrough to `python manage.py`. |

Universal flags before the subcommand (`--quiet`, `--verbose`,
`--log-file`, `--no-color`, `--color`, `--no-input`); per-command
flags after (`--json`, `--dry-run`, `--yes`, `--force`).

## Differences from Laravel + Symfony

| Aspect | Laravel | Symfony | Django |
|--------|---------|---------|--------|
| Writable tree | `storage/` + `bootstrap/cache/` | `var/` | `media/` + `staticfiles/` |
| App secret | `APP_KEY=base64:...` | `APP_SECRET=...` (hex) | `SECRET_KEY=...` (Django alphabet) |
| Env file | `.env` (gitignored) | `.env.local` (gitignored) | `.env` (django-environ / decouple convention) |
| Console | `artisan` (root) | `bin/console` | `manage.py` (root) |
| Console runtime | `php` | `php` | `python` |
| Scheduler | `schedule:run` every minute | none — use `shimkit cron add` | none — use `shimkit cron add` |

## perms

`media/` (user uploads) and `staticfiles/` (collectstatic target)
are the canonical writable trees in modern Django layouts.
`staticfiles/` typically doesn't exist on a fresh project until
the first `collectstatic` — shimkit warns about that and runs
the global `chmod` passes regardless.

Group detection: `getent group <name>` on Linux, `dscl . -read
/Groups/<name>` on macOS, `grp.getgrnam()` Python fallback.

```bash
shimkit framework django perms --yes ./my-django-app
shimkit framework django perms --yes --group staff ./my-django-app  # macOS
shimkit framework django perms --dry-run ./my-django-app
```

## env

Writes `.env` with a generated `SECRET_KEY` + `DATABASE_URL` +
sensible dev defaults. **Refuses to overwrite** an existing
`.env`. The format is django-environ / python-decouple
compatible: `KEY=value` lines. `DATABASE_URL` follows the
Heroku / dj-database-url convention.

`SECRET_KEY` is 50 chars from Django's documented alphabet —
matches what `django.core.management.utils.get_random_secret_key()`
would emit, but shimkit doesn't depend on Django being installed
to scaffold the file.

Default DB engine is **postgres** (Django's most-shipped pairing).
Override with `--db mysql` or `--db mariadb`.

| `--db`     | URL prefix | Port |
|------------|------------|------|
| `postgres` (default) | `postgres://` | 15432 |
| `mysql`    | `mysql://`    | 13306 |
| `mariadb`  | `mysql://`    | 13307 |

```bash
shimkit db postgres up
shimkit framework django env --yes --db postgres ./my-app

# DEBUG=False for a more prod-like local
shimkit framework django env --yes --no-debug ./my-app
```

The env file also lists a commented-out `REDIS_URL` line as a
hint pointing the user at `shimkit db redis up` (v0.15.0+).

## migrate

Sugar for `manage migrate --no-input`:

```bash
shimkit framework django migrate ./my-app
shimkit framework django migrate --in-container --stack myapp ./my-app
```

## manage

Generic passthrough to `python manage.py`. Host execution by
default — preflights `python` via
`shimkit.core.version.preflight`, exits 69 with the remediation
hint when `python` is missing. `--in-container` routes through
`shimkit stack lemp`'s php-fpm container (which has `python`
installed via the upstream PHP-FPM image's base layers).

```bash
shimkit framework django manage --project ./my-app -- runserver 0.0.0.0:8000
shimkit framework django manage --project ./my-app -- createsuperuser
shimkit framework django manage --project ./my-app -- collectstatic --no-input
```

`--project` defaults to the current working directory.

## End-to-end example

```bash
# 1. Database
shimkit db postgres up

# 2. Optional: Redis cache / Channels
shimkit db redis up

# 3. Scaffold env + fix perms
shimkit framework django env  --yes --db postgres ./my-app
shimkit framework django perms --yes ./my-app

# 4. Migrate + create superuser
shimkit framework django migrate ./my-app
shimkit framework django manage --project ./my-app -- createsuperuser

# 5. Run the dev server
shimkit framework django manage --project ./my-app -- runserver
```

## Configuration

```json
{
  "tools": {
    "framework": {
      "django": {
        "web_group": "www-data",
        "file_mode": "664",
        "dir_mode": "775",
        "writable_dirs": ["media", "staticfiles"],
        "default_debug": true
      }
    }
  }
}
```

Override `web_group` per host. Add `writable_dirs` entries if
your app writes outside `media/` + `staticfiles/`.

## Exit codes

| Code | Meaning |
|-----:|---------|
| 0    | success |
| 1    | bad path, missing `manage.py`, refusing overwrite, prompt cancelled |
| 2    | Typer usage error |
| 69   | `EX_UNAVAILABLE` — wrong platform or missing `python` for `manage`/`migrate` |
| 130  | SIGINT |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | full. Dev account typically owns the project, so `chgrp` is no-op'd unless `--group` is passed. |
| Linux    | full. Targets `www-data` by default; override with `--group`. |
| WSL      | works (Linux path). |
| Windows  | out of charter (use WSL). |
