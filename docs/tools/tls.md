# shimkit tls

TLS certificate lifecycle helper. Container-first: every certbot
invocation is a one-shot through the upstream `certbot/certbot`
image. The `/etc/letsencrypt` directory is bind-mounted at
`~/.shimkit/data/tls/etc-letsencrypt/` so account + cert state
survives container exits and host reboots.

## Commands

| Command | Purpose |
|---------|---------|
| `shimkit tls`                                                        | Menu. |
| `shimkit tls request -d D [-d D2 ...] --email E --webroot PATH [--staging]` | MODERATE. Request a new cert via webroot ACME challenge. |
| `shimkit tls list [--json]`                                          | Enumerate local certs with expiry dates. |
| `shimkit tls status DOMAIN [--json]`                                 | Show one cert's paths + expiry. |
| `shimkit tls renew [-d DOMAIN] [--force-renewal]`                    | MODERATE. Renew certs (all due, or one named). |
| `shimkit tls revoke -d DOMAIN --confirm REVOKE-TLS`                  | SEVERE. Revoke a cert via the ACME CA. |
| `shimkit tls cron-install [--schedule S]`                            | MODERATE. Install a daily `shimkit tls renew` cron entry. |

Universal flags before the subcommand (`--quiet`, `--verbose`,
`--log-file`, `--no-color`, `--color`, `--no-input`); per-command
flags after (`--json`, `--dry-run`, `--yes`, `--force`).

## How it works

### Webroot (HTTP-01, default)

`shimkit tls request --method webroot` runs:

```
docker run --rm \
  -v ~/.shimkit/data/tls/etc-letsencrypt:/etc/letsencrypt \
  -v ~/.shimkit/data/tls/var-lib-letsencrypt:/var/lib/letsencrypt \
  -v <webroot>:/webroot:ro \
  certbot/certbot:v3.0.1 \
  certonly --non-interactive --agree-tos \
  --email ops@example.com \
  --webroot -w /webroot \
  -d example.com [-d www.example.com] \
  [--staging]
```

### DNS-cloudflare (DNS-01, v0.13.0+)

`shimkit tls request --method dns-cloudflare` runs:

```
docker run --rm \
  -v ~/.shimkit/data/tls/etc-letsencrypt:/etc/letsencrypt \
  -v ~/.shimkit/data/tls/var-lib-letsencrypt:/var/lib/letsencrypt \
  -v <credentials-parent-dir>:/credentials:ro \
  certbot/dns-cloudflare:v3.0.1 \
  certonly --non-interactive --agree-tos \
  --email ops@example.com \
  --dns-cloudflare \
  --dns-cloudflare-credentials /credentials/cloudflare.ini \
  --dns-cloudflare-propagation-seconds 60 \
  -d example.com [-d '*.example.com'] \
  [--staging]
```

**Required for wildcards.** `*.example.com` certs only work via
DNS-01. The Cloudflare plugin needs a Cloudflare API token with
`Zone:DNS:Edit` scope on the zone you're issuing for.

**Credentials file format** (one line):

```ini
dns_cloudflare_api_token = your-cloudflare-api-token-here
```

**Mode 0600 required.** certbot refuses any credentials file that's
group- or world-readable; shimkit refuses up-front with a clear
error before invoking the container. Run `chmod 600 cloudflare.ini`
before passing it.

The parent directory of the credentials file is mounted at
`/credentials` inside the container, read-only. So
`/secrets/cloudflare.ini` on the host becomes
`/credentials/cloudflare.ini` inside.

The webroot must already be served at
`http://<domain>/.well-known/acme-challenge/` for the ACME challenge
to succeed. The recommended layout for `shimkit web nginx vhost`-
generated vhosts is the project root.

`certbot/certbot:v3.0.1` is the default; override via
`tools.tls.certbot_image` in your user config. Pinning to a
specific version rather than `:latest` keeps renewal behaviour
deterministic.

## On-disk layout

```
~/.shimkit/data/tls/
├── etc-letsencrypt/         # mounts to /etc/letsencrypt
│   ├── live/<domain>/       # symlinks (fullchain.pem, privkey.pem, ...)
│   ├── archive/<domain>/    # numbered cert history
│   ├── accounts/            # ACME account keys + metadata
│   └── renewal/             # renewal config per cert
└── var-lib-letsencrypt/     # mounts to /var/lib/letsencrypt
```

Point nginx at `fullchain.pem` + `privkey.pem` from the `live/`
directory — they're stable symlinks that get repointed each
renewal, so nginx never needs to be told a new cert path.

## Examples

```bash
# Webroot (HTTP-01) — Request a cert in staging first (recommended —
# Let's Encrypt rate-limits production aggressively, but staging is
# forgiving).
shimkit tls request --yes --staging \
    --email ops@example.com \
    --webroot /var/www/example \
    -d example.com -d www.example.com

# Once staging works, request the real cert.
shimkit tls request --yes \
    --email ops@example.com \
    --webroot /var/www/example \
    -d example.com -d www.example.com

# DNS-cloudflare (DNS-01) — required for wildcards.
echo 'dns_cloudflare_api_token = YOUR-TOKEN-HERE' > ~/.secrets/cloudflare.ini
chmod 600 ~/.secrets/cloudflare.ini
shimkit tls request --yes --staging \
    --email ops@example.com \
    --method dns-cloudflare \
    --credentials ~/.secrets/cloudflare.ini \
    -d example.com -d '*.example.com'

# Enumerate local certs.
shimkit tls list
shimkit tls list --json

# Inspect a single cert.
shimkit tls status example.com
shimkit tls status example.com --json

# Renew everything that's within 30 days of expiry.
shimkit tls renew --yes

# Force a renewal even if the cert isn't due (test, key rotation).
shimkit tls renew --yes --force-renewal -d example.com

# Install the daily renewal cron entry (default: 03:17 every day).
shimkit tls cron-install --yes

# Custom schedule.
shimkit tls cron-install --yes --schedule "0 4 * * *"

# Revoke (SEVERE — confirm token required).
shimkit tls revoke -d example.com --confirm REVOKE-TLS
```

## Configuration

```json
{
  "tools": {
    "tls": {
      "data_dir": "~/.shimkit/data/tls",
      "certbot_image": "certbot/certbot:v3.0.1",
      "default_method": "webroot",
      "default_email": null,
      "renewal_schedule": "17 3 * * *",
      "revoke_severe_token": "REVOKE-TLS"
    },
    "versions": {
      "openssl": {"min": "1.1"}
    }
  }
}
```

`default_email` set in the user config lets you drop `--email`
from every `shimkit tls request` invocation. `tools.versions.openssl`
is the floor used by `shimkit doctor` and the cert-expiry parsing
in `tls list` / `tls status` (which shells out to `openssl x509
-enddate`).

## Exit codes

| Code | Meaning |
|-----:|---------|
| 0    | success |
| 1    | invalid input, missing webroot, certbot failed, missing cert, missing severe token |
| 2    | Typer usage error |
| 69   | `EX_UNAVAILABLE` — docker missing / daemon unreachable / out-of-range |
| 130  | SIGINT |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | full (Docker Desktop required). |
| Linux    | full. |
| WSL      | full (Docker Desktop or native Docker). |
| Windows  | out of charter — use WSL. |

## Notes

- **Staging first.** Let's Encrypt's production rate limits are
  punishing (5 failed validations / hour / hostname). Always
  pass `--staging` for first runs; the resulting cert isn't
  trusted but proves the webroot setup works.
- **Webroot vs DNS-01.** Both are wired as of v0.13.0. Webroot
  (HTTP-01) is the default; DNS-01 via Cloudflare is opt-in via
  `--method dns-cloudflare` and is the **only** path to wildcard
  certs. Other DNS providers (Route53, DigitalOcean, etc.) each
  need their own credential surface and are deferred.
- **No PyPI extra.** This tool reuses the `[docker-clean]`
  extra's `docker` package — no new install footprint.
- **Renewal cadence.** Let's Encrypt certs are valid for 90 days;
  certbot's `renew` only renews within 30 days of expiry, so the
  daily cron is safe (and idempotent — no-op when nothing's due).
