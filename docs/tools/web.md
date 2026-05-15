# shimkit web

Parent sub-app for web-server tooling. One tool today (`nginx`);
`tls` / `apache` / `caddy` are future siblings.

## shimkit web nginx vhost

Hardened nginx vhost generator. **Default mode is file-only** —
`shimkit web nginx vhost generate` writes a vhost file to stdout
(or `--out PATH`) and never touches `/etc/nginx/`. Mutating the
host is opt-in via `apply` / `remove`, both gated behind SEVERE
tokens.

### Commands

| Command                                                    | Purpose                                                   |
|------------------------------------------------------------|-----------------------------------------------------------|
| `shimkit web nginx vhost generate --name NAME --domain HOST --root PATH [--flavor F] [--php-version V] [--out P]` | Render a vhost. File-only. Idempotent.                    |
| `shimkit web nginx vhost apply --name NAME --source PATH --confirm APPLY-VHOST` | **SEVERE.** Install to `sites-available/`, symlink to `sites-enabled/`, reload nginx. |
| `shimkit web nginx vhost remove --name NAME --confirm REMOVE-VHOST` | **SEVERE.** Disable + remove a shimkit-managed vhost; reload nginx. |
| `shimkit web nginx vhost list [--json]`                    | List vhosts at `sites-enabled/`; flag which shimkit manages. |

### Flavors

| `--flavor` | Use case                                | What's special                                       |
|------------|-----------------------------------------|------------------------------------------------------|
| `static`   | Built SPA bundle, docs site             | `try_files $uri $uri/ =404;` — no PHP block          |
| `php`      | Generic PHP app                         | `try_files $uri $uri/ /index.php?$args;` + FPM block |
| `laravel`  | Laravel app                             | Same as `php` but `root → $ROOT/public`              |

Every flavor carries the same security-header baseline:

- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: no-referrer-when-downgrade`
- `Permissions-Policy: interest-cohort=()`
- `server_tokens off;`
- `location ~ /\.(?!well-known)` — deny dotfile access

HSTS is **deliberately not included by default**. It's a footgun
on HTTP-only hosts (browsers cache the policy and refuse downgrade).
Turn it on once you've verified TLS works end-to-end and have a
plan for cert renewal.

### Examples

```bash
# Generate a static docs vhost to stdout
shimkit web nginx vhost generate \
    --name docs --domain docs.local --root /srv/docs --flavor static

# Generate a Laravel vhost and write to a file
shimkit web nginx vhost generate \
    --name myapp --domain myapp.local --root /var/www/myapp --flavor laravel \
    --out /tmp/myapp.conf

# Override the PHP-FPM socket version
shimkit web nginx vhost generate \
    --name myapp --domain myapp.local --root /var/www/myapp --flavor php \
    --php-version 8.1

# JSON output (good for templating into other tools)
shimkit web nginx vhost generate --name docs --domain docs.local --root /srv/docs --json
```

### Apply (SEVERE)

```bash
# 1. Generate to a tmp file
shimkit web nginx vhost generate --name docs --domain docs.local --root /srv/docs --out /tmp/docs.conf

# 2. Apply with the severe token
sudo shimkit web nginx vhost apply --name docs --source /tmp/docs.conf --confirm APPLY-VHOST
```

`apply` is layered:

1. Verifies the source file carries the `# managed-by: shimkit`
   marker. Refuses non-shimkit-generated vhosts. This forces the
   `generate → apply` workflow rather than blind file-copies.
2. Verifies the target path (`sites-available/<name>`) is either
   missing or already shimkit-managed. Refuses to clobber an
   admin-authored vhost.
3. `sudo install -m 0644 -o root <tmp> sites-available/<name>` —
   atomic.
4. `sudo ln -sfn sites-available/<name> sites-enabled/<name>`.
5. `sudo nginx -s reload`. If reload fails, the vhost is in place
   but warns the user to run `nginx -t` for diagnostics.

### Remove (SEVERE)

```bash
sudo shimkit web nginx vhost remove --name docs --confirm REMOVE-VHOST
```

Same managed-marker check protects against removing external
vhosts. Unlinks `sites-enabled/<name>`, deletes
`sites-available/<name>`, reloads nginx.

### List

```bash
shimkit web nginx vhost list
shimkit web nginx vhost list --json
```

Walks `sites-enabled/`. Each entry is tagged `[shimkit]` or
`[external]` based on the managed marker; `--json` returns the
same structure programmatically.

## JSON example

```bash
$ shimkit web nginx vhost generate --name docs --domain docs.local --root /srv/docs --json
{
  "ts": "...",
  "tool": "web.nginx",
  "step": "vhost.generate",
  "status": "ok",
  "data": {
    "name": "docs",
    "domain": "docs.local",
    "root": "/srv/docs",
    "flavor": "static",
    "php_version": "8.3",
    "body": "# managed-by: shimkit\n# Flavor: static\n..."
  }
}
```

## Configuration

```json
{
  "tools": {
    "web": {
      "nginx": {
        "sites_available_dir": "/etc/nginx/sites-available",
        "sites_enabled_dir":   "/etc/nginx/sites-enabled",
        "reload_cmd":          ["nginx", "-s", "reload"],
        "apply_severe_token":  "APPLY-VHOST",
        "remove_severe_token": "REMOVE-VHOST",
        "default_php_version": "8.3",
        "default_flavor":      "static",
        "managed_marker":      "# managed-by: shimkit"
      }
    }
  }
}
```

RHEL-family hosts use `/etc/nginx/conf.d/` only (no `sites-*`
directories). Set `sites_available_dir` and `sites_enabled_dir` to
the same path in your user config and the apply path still works
— `ln -sfn` collapses to "the file is already there" when source
and dest are identical inodes.

## Exit codes

| Code | Meaning                                                       |
|-----:|---------------------------------------------------------------|
| 0    | success / no-op                                               |
| 1    | unknown flavor / missing source / no managed marker / SEVERE-token missing |
| 2    | Typer usage error                                             |
| 69   | EX_UNAVAILABLE — wrong platform; `nginx` not on PATH (apply only) |
| 130  | SIGINT                                                        |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | ✓ — generate works always; apply targets macOS nginx paths if configured. |
| Linux    | ✓ — generate + apply against `/etc/nginx/sites-{available,enabled}`. |
| WSL      | ✓ (Linux path).                                                  |
| Windows  | ✗ — out of charter.                                              |

## Charter notes

The original ubuntu `nginx:host.sh` shipped one vhost template
with hardcoded `php8.0-fpm` socket and no marker. shimkit borrows
the security-header set (the genuinely good bit), parameterises
the PHP version, adds the managed-marker safety, and gates the
host-mutation path behind two SEVERE tokens (`APPLY-VHOST`,
`REMOVE-VHOST`). The default mode — `generate` to a file — is
where most users will live.
