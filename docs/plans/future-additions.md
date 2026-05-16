# Future additions

Naturally-extensible surface that could be built on top of the
current shape **if and when a concrete user need surfaces**. These
are not deferrals (the way `shimkit cron` and `--on-host` were
deferred from v0.5.0 → v0.6/v0.9) and they're not commitments. They
exist here so the next contributor / future-me has a written
record of "this slot is well-defined, the design pattern is clear,
nobody's asking for it yet."

For things actually deferred to a specific future release, see
[`known-issues.md`](known-issues.md). For things deliberately
chosen against, see
[`.design/plans/feature-gap-analysis.md`](../../.design/plans/feature-gap-analysis.md)'s
**Skip** column.

---

## TLS / ACME — more DNS-01 providers

Two providers shipped (v0.13.0 Cloudflare, v0.17.0 Route53). The
shape for adding a third is well-understood: a provider-specific
container image with the right certbot plugin, a per-provider
credentials-mount path, a `Literal["dns-<provider>"]` widening,
and a `tools.tls.{certbot_dns_<provider>_image,
<provider>_propagation_seconds}` config pair.

Plausible next providers, ranked by ACME ecosystem usage:

| Provider | certbot image | Credentials shape |
|----------|---------------|-------------------|
| **DigitalOcean** | `certbot/dns-digitalocean` | `dns_digitalocean_token = <pat>` (one line, like Cloudflare) |
| **Hurricane Electric** | community plugin (no official `certbot/dns-he` image) | username + password |
| **Google Cloud DNS** | `certbot/dns-google` | service-account JSON file |
| **Linode** | `certbot/dns-linode` | `dns_linode_key = <token>` |
| **OVH** | `certbot/dns-ovh` | application key + secret + consumer key |

Each is ~100 LOC + ~10 tests in the established pattern. Pick one
when the first user asks.

---

## Framework recipes — more siblings

Three shipped (v0.7 Laravel, v0.14 Symfony, v0.16 Django). The
pattern is well-understood:

1. `perms` — fix permissions on the framework's writable tree.
2. `env` — scaffold the framework's env-file shape with a
   generated app secret + sensible `DATABASE_URL`.
3. One framework-specific shortcut (`migrate` / `cache-clear` /
   `cron-install` / etc).
4. Generic console passthrough — host by default, `--in-container`
   for stack lemp.

Plausible next recipes:

| Framework | Console | Secret | Writable tree | Likely shortcut |
|-----------|---------|--------|---------------|-----------------|
| **Ruby on Rails** | `rails` (or `bin/rails`) | `Rails.application.credentials.secret_key_base` | `tmp/` + `log/` + `public/uploads/` | `db:migrate` |
| **Next.js** | `next` | `.env.local` `NEXTAUTH_SECRET` | `.next/` + `node_modules/` | `next build` |
| **Express / Node** | varies | — | varies | varies — probably too project-shaped, skip |
| **FastAPI** | — | — | — | dotfile / Dockerfile territory, skip |
| **Flask** | `flask` | env-var | `instance/` | `db.create_all` (via `flask shell`) |

Each is ~200 LOC + ~25 tests in the Laravel/Symfony/Django mould.

---

## DB engines — more registry entries

Six shipped (mysql / mariadb / postgres / mongo / redis /
phpmyadmin). The pattern is:

1. New file under `tools/db/engines/<name>.py` with an `Engine`
   subclass.
2. Add to the `REGISTRY` dict in `engines/__init__.py`.
3. Add a `DbEngineEntry` line in `defaults.json` +
   `schema.py::engines` default.
4. Optionally override `up_command()` (Redis pattern) for argv-
   passed config.
5. Decide `supports_dump` / `supports_on_host`.

Plausible next engines:

| Engine | Image | Port | Notes |
|--------|-------|-----:|-------|
| **valkey** | `valkey/valkey:7-alpine` | `:16380` | Redis fork; same shape as Redis (`up_command` overrides). One-line `s/redis/valkey/g` plus the image swap. |
| **elasticsearch** | `elasticsearch:8` | `:19200` | Single-node config via `discovery.type=single-node` env var. Heap settings (`ES_JAVA_OPTS`). `supports_dump=False` (snapshots are repo-based). |
| **opensearch** | `opensearchproject/opensearch:2` | `:19200` | Apache 2.0 ES fork. Same shape; `OPENSEARCH_INITIAL_ADMIN_PASSWORD` env var. |
| **kafka** | `apache/kafka:3.7` or `confluentinc/cp-kafka` | `:19092` | Heavier — needs Zookeeper OR KRaft mode. Probably needs a multi-container stack recipe (`shimkit stack kafka`) rather than a single-engine entry. |
| **minio** | `minio/minio:latest` | `:19000` + `:19001` (console) | S3-compatible. Two ports. Needs `command` override for `server /data --console-address :9001`. |
| **clickhouse** | `clickhouse/clickhouse-server` | `:18123` (HTTP) + `:19000` (native) | Two ports. Default user `default` with no password — would need a config injection for AUTH. |

Each is ~150 LOC + ~15 tests in the engine-driver pattern.

---

## `--on-host` for `stack lemp` — out of charter

Initially scoped in the v0.5.0 plan as a deferred `v0.7+`
candidate. **Won't be built.**

The LEMP recipe is intrinsically multi-container: db + php-fpm +
nginx on a per-project user-defined bridge network. The Docker-
first design IS the value here — replicating the same shape on
the host means coordinating three host packages (mysql + php-fpm
+ nginx), their config files, a shared user/group, and the
inter-process communication paths that the bridge network gives
for free in the container path.

Users who want host-installed components can:

1. **Mix and match.** `shimkit db postgres up --on-host` plus
   `shimkit stack lemp up` will work — the stack's php-fpm
   container reaches the host db via `host.docker.internal` (or
   `host-gateway` on Linux).
2. **Skip the recipe entirely.** Brew/apt-install nginx +
   php-fpm + mysql themselves and run them via systemd /
   `brew services`. The original `ubuntu/` scripts did exactly
   this and had **five Critical security flags** (apparmor
   disable, mysql 0.0.0.0 bind, etc.) — shimkit's containerised
   LEMP is the safer path.

The v0.9.0 `--on-host` for `shimkit db` covers the "I want a
local db without Docker" need without inheriting the LEMP
recipe's coupling complexity. That's the supported escape hatch.

If a future user has a specific need for host-LEMP that isn't
covered by either of the two paths above, the right move is to
document the path explicitly here as a deferral rather than
silently building an opt-in mode that re-introduces audit-flagged
patterns.

---

## How to graduate an item

When a concrete user shows up wanting one of these:

1. Move the item to a `v0.X.0-<name>.md` plan doc with the
   detailed surface, LOC estimate, test plan, and any open
   design questions.
2. Cross-link from `known-issues.md` (so it's tracked alongside
   the other in-flight deferrals).
3. Build it on the next available release cycle.
4. When shipped, delete the entry here and add the cross-link
   in the relevant release notes.

The bar is **"someone is asking for it"** — not **"it would be
nice to have"**. shimkit's existing surface is broad enough that
adding more sub-apps purely on aesthetic grounds will slowly
turn each `shimkit <tool>` boot into a Typer cold-start tax.
