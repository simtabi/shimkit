# shimkit documentation

The repo root has the short version. This directory has the long
version.

## Getting started

- **[Installation](installation.md)** — uv, pipx, pip, Homebrew, the
  curl one-liner, and how `shimkit self-update` works.
- **[Configuration](configuration.md)** — the JSON config layer, where
  files live, override precedence, the schema.

## Tools

shimkit is a collection. Each tool gets its own page:

- **[`shimkit java`](tools/java.md)** — OpenJDK version manager.
  Install / list / switch / upgrade / uninstall / remove-oracle.
- **[`shimkit shell`](tools/shell.md)** — Cross-PM shell upgrader for
  bash / zsh / fish / ksh.
- **[`shimkit dns`](tools/dns.md)** — macOS DNS resolver recovery.
  Diagnose, flush, fix (6-step escalation), test, rollback.
- **[`shimkit adguard`](tools/adguard.md)** — AdGuard Home port-conflict
  fixer (Linux). API-first, ruamel.yaml fallback.
- **[`shimkit docker-clean`](tools/docker-clean.md)** — Docker resource
  cleanup (Linux + macOS + WSL). docker-py SDK + buildx-aware prune.
- **[`shimkit tls`](tools/tls.md)** — TLS cert lifecycle via
  container-first certbot. request / list / status / renew /
  revoke (SEVERE) / cron-install.
- **[`shimkit framework laravel`](tools/framework-laravel.md)** —
  Laravel helpers: perms, `.env` scaffold, scheduler cron-install,
  artisan passthrough (host or LEMP container).

Top-level utilities (not tools):

- `shimkit config` — inspect, edit, validate user configuration.
  Documented in [Configuration](configuration.md).
- `shimkit doctor` — system diagnostics for bug reports. No dedicated
  page; run it and the output is self-documenting.
- `shimkit self-update` — keep shimkit current. Documented in
  [Installation](installation.md#updates).

## Development

- **[Architecture](architecture.md)** — how the core/tools split
  works, the load-bearing rules, how to add a new tool.
- **[Onboarding](onboarding.md)** — practical walkthrough for getting
  productive: setup, the 5 rules with grep recipes, the canonical
  recipe for adding a new tool, common dev tasks, debugging guide.
- **[Release process](release.md)** — cutting a new version, the CI
  pipeline, what each release job does.
- **[Shipping checklist](shipping-checklist.md)** — every step from
  "code ready" to "users can install", in dependency order. Tracks
  what's done vs what still needs your action.
- **[Validation scope](validation-scope.md)** — what's in scope for
  automated + manual gates, what's deliberately out of scope, and
  how to expand the envelope.
- **[Known issues + pending items](plans/known-issues.md)** — checks
  that exist in our scope but can't be automated (and why), coverage
  deferrals, and aspirational follow-ups without owners.

## Release notes

Per-version, user-facing summaries (newest first):

- **[`v0.10.0`](release-notes/v0.10.0.md)** — coverage push 74% → 85%
  (+397 tests). No code changes.
- **[`v0.9.0`](release-notes/v0.9.0.md)** — `shimkit db --on-host`
  for mysql/mariadb/postgres. Manages existing host installs;
  refuses to install packages (the audit-completion bit).
- **[`v0.8.0`](release-notes/v0.8.0.md)** — `shimkit tls` (certbot
  container-first cert lifecycle). State at
  `~/.shimkit/data/tls/`; webroot ACME; daily renewal cron.
- **[`v0.7.1`](release-notes/v0.7.1.md)** — version-drift recovery
  for v0.7.0.
- **[`v0.7.0`](release-notes/v0.7.0.md)** — `shimkit framework
  laravel` (perms / env / cron-install / artisan). First framework
  recipe under the new `framework` parent.
- **[`v0.6.0`](release-notes/v0.6.0.md)** — `shimkit cron` (generic
  user-crontab editor). Atomic write + backup-on-mutate.
- **[`v0.5.0`](release-notes/v0.5.0.md)** — ubuntu/ migration:
  three new sub-trees (`db`/`stack`/`web`), two new core
  primitives (`core/docker`, `core/version`), 152 new tests. Five
  Critical audit flags dissolved by Docker-first design.
- **[`v0.2.0`](release-notes/v0.2.0.md)** — three new tools (`dns`,
  `adguard`, `docker-clean`); uniform CLI surface across all new
  subcommands; argv-list PM templates; container hardening + SBOM
  + attestation.

External references:

- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — coding conventions, test
  patterns, PR expectations.
- [`SECURITY.md`](../SECURITY.md) — vulnerability disclosure.
- [`CHANGELOG.md`](../CHANGELOG.md) — release history.

For shimkit-specific release operations, see
[`release.md`](release.md). For the wider org-level reference on
publishing to PyPI / npm / Docker registries, ask the team — that
guide lives outside this repo.
