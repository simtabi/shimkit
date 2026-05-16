# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.19.0] — 2026-05-16

### Added

- `docs/plans/future-additions.md` — captures the naturally-
  extensible surface (more TLS DNS-01 providers, more framework
  recipes, more db engines) with concrete patterns but no
  current user demand. Documents the bar to graduate an item
  ("someone is asking for it" — not "it would be nice to
  have"). Also captures the **rejected** `--on-host` for
  `stack lemp` with the reasoning.
- `docs/plans/shipping-audit.md` — comprehensive shipped-vs-
  pending walk through every plan / design spec / doc in the
  repo. Migration W1-W9 (all shipped), feature-gap-analysis
  defer list (all shipped + 1 rejected with rationale),
  validation-report TODOs (all closed out), cleanup-2026-05-14
  deferrals (both shipped in v0.10 / v0.12), shipping-checklist
  phases (all in-code items shipped). Captures the two **user-
  side actions** that aren't deferrals: PyPI trusted-publisher
  config + branch protection on `main`. Includes step-by-step
  for each plus the retroactive PyPI re-upload recipe for the
  10+ pending tags (v0.11.0 through v0.18.0). Documents the 16
  permanent skips with rationale (NM real-link-event check +
  the 15 ubuntu-source Skip items). Concludes "the plans tree
  is drained — no item is silently orphaned."

Both files linked from docs/README.md Development section.

### Notes

Doc-only release. No source-code changes. The two plans docs were
already pushed to `main` as chores ahead of this release; v0.19.0
tags the existing tree and ships a release-notes entry so the
docs index has a clear "this is the version where the audit
landed" pointer.

Gates: pytest 1130 passed, ruff clean, mypy strict clean.

## [0.18.0] — 2026-05-16

### Changed

- `README.md` — synced to v0.17.0 reality:
  - `db` description: 5 engines → 6 engines (mysql / mariadb /
    postgres / mongo / redis / phpmyadmin) + `--on-host` mode
    note for the three SQL engines.
  - `tls` description: webroot-only → three ACME methods
    (webroot / dns-cloudflare / dns-route53).
  - Top-level help-text panel: `framework` description widened
    from "Laravel today" to "Laravel + Symfony + Django".
  - Framework recipes section: added Symfony + Django bullets
    alongside Laravel.
  - Documentation table: added Symfony + Django deep-dive rows.
- `docs/architecture.md` — `core/` and `tools/` directory
  listings refreshed to mention v0.6-v0.17 additions inline
  (redis engine in db/, dns-cloudflare + dns-route53 in tls/,
  symfony + django alongside laravel in framework/).
- `docs/onboarding.md` — sub-app tree diagram expanded from 5
  tools to all 18 currently registered, with a parenthetical
  for `framework`'s three sibling recipes.
- `docs/tools/cron.md` — "Charter notes" section: the
  "v0.7+ candidate" line is now a "v0.7.0 shipped" note
  pointing at Laravel's cron-install; mentions Symfony + Django
  don't ship cron-install (no built-in scheduler).
- `config/shimkit.schema.json` — regenerated from the pydantic
  schema. Now includes redis engine, framework.symfony +
  framework.django blocks, tls.certbot_dns_route53_image +
  route53_propagation_seconds fields, db.host_services map.

### Notes

Doc-only release. No source-code changes. The schema-regen
output is committed alongside the pydantic source so external
JSON-schema consumers see the current shape without needing to
run the regen command themselves.

Gates: pytest 1130 passed, ruff clean, mypy strict clean.

## [0.17.0] — 2026-05-16

### Added

- **`shimkit tls --method dns-route53`** — AWS Route53 DNS-01
  alongside the v0.13.0 Cloudflare path. Uses the upstream
  `certbot/dns-route53:v3.0.1` image (auto-selected when
  `--method dns-route53` is passed).
- `tools.tls.certbot_dns_route53_image` config field — pin the
  Route53 plugin image independently.
- `tools.tls.route53_propagation_seconds` config field — same
  range (`[0, 600]`) as the Cloudflare equivalent. Default `60`.

### Changed

- `certbot.container_volumes` accepts a `credentials_mount`
  parameter (`"cloudflare"` or `"route53"`). Cloudflare keeps the
  v0.13.0 behaviour of mounting the credentials file's parent
  directory at `/credentials`; Route53 mounts the file itself at
  `/root/.aws/credentials` (boto3's default search path — no
  `--dns-route53-credentials` flag exists).
- `certbot.request_argv` accepts `method="dns-route53"`. Emits
  `--dns-route53` + `--dns-route53-propagation-seconds`.
- `TlsConfig.default_method` widened to include `"dns-route53"`.
- `tls request` `--credentials` flag help text covers both
  Cloudflare token format and AWS credentials file format.

### Tests

- 14 new tests in `tests/test_tools_tls_dns_route53.py` (1116 →
  1130 total). Pure argv-builder shape (Route53 flags +
  propagation + staging/dry-run; webroot + cloudflare paths
  unaffected), container_volumes route53 mount target
  (`/root/.aws/credentials` vs Cloudflare's `/credentials`),
  manager validation (missing-credentials / missing-file /
  loose-mode refusal / happy path picks dns-route53 image /
  uses route53_propagation_seconds not cloudflare's / JSON
  output includes method), config plumbing (route53 image +
  propagation_seconds range validation).
- Adjusted one Cloudflare test that previously used `dns-route53`
  as the "unknown method" placeholder — now uses
  `dns-digitalocean`.

### Notes

Second DNS-01 provider. Cloudflare + Route53 cover the two
most-used providers in the ACME ecosystem. Other providers
(DigitalOcean, Hurricane Electric, etc.) each need their own
credential surface and provider-specific image — opt-in extras
in a future release.

Gates: pytest 1130 passed, ruff clean, mypy strict clean. No new
optional dependency extras.

## [0.16.0] — 2026-05-16

### Added

- **`shimkit framework django`** — third framework recipe.
  Modelled on Laravel + Symfony with Django-specific
  conventions:
  - `perms PATH [--group G]` (MODERATE) — fixes `media/` +
    `staticfiles/` permissions.
  - `env PATH [--name N] [--debug/--no-debug] [--db D]` (MODERATE)
    — scaffolds `.env` with `SECRET_KEY` (Django's 50-char
    alphabet) + `DATABASE_URL` (dj-database-url / django-environ
    convention). Refuses to overwrite. Default DB is **postgres**
    (Django's most common pairing); mysql + mariadb also
    supported.
  - `migrate PATH` — sugar for `manage migrate --no-input`.
  - `manage -- <args>` — passthrough to `python manage.py`.
    Host or `--in-container` via `shimkit stack lemp`.
- `tools.framework.django` config block with `web_group`,
  `file_mode`, `dir_mode`, `writable_dirs`, and `default_debug`.

### Tests

- 30 new tests in `tests/test_tools_framework_django.py` (1086 →
  1116 total). _generate_secret_key (length / Django alphabet /
  uniqueness across 100 calls), platform gating, perms (path
  refusal / dry-run / media + staticfiles targeting / chgrp skip
  on missing group / missing-writable warning / failed-step JSON),
  env (overwrite refusal / SECRET_KEY shape + DATABASE_URL
  postgres default / DEBUG True default / --no-debug flag /
  DATABASE_URL mysql + mariadb / ALLOWED_HOSTS + EMAIL_BACKEND
  present / Redis hint commented-out / dry-run no-write /
  uniqueness across two scaffolds), manage (host happy path /
  missing-python exits 69 / no-args refusal / missing-manage.py
  refusal / --in-container delegates to StackManager), migrate
  (wraps manage migrate --no-input), command surface (framework
  --help lists django; django --help lists all four
  subcommands).

### Notes

Third framework recipe. Same shape pattern as Laravel + Symfony:
perms / env / passthrough + one framework-specific shortcut
(`migrate` for Django, `cache-clear` for Symfony,
`cron-install` for Laravel). No cron-install for Django —
same reason as Symfony, no built-in scheduler.

Gates: pytest 1116 passed, ruff clean, mypy strict clean. No new
optional dependency extras.

## [0.15.0] — 2026-05-16

### Added

- **`shimkit db redis`** — sixth engine in the `db` registry.
  Image `redis:7-alpine`, host port `:16379`, container port 6379.
  AUTH via `--requirepass` (Redis's official image doesn't read
  a `REDIS_PASSWORD` env var), AOF persistence on by default.
- **`Engine.up_command(password)`** — new method on the engine
  ABC. Default returns `None` (use image's default CMD). Redis
  overrides to return `["redis-server", "--requirepass", PW,
  "--appendonly", "yes"]`. Available to any future engine that
  needs argv-passed config the image doesn't expose as env vars.
- `Redis` engine driver in `tools/db/engines/redis.py`. Marks
  `supports_dump=False` (Redis backups are volume-level RDB
  snapshots, not logical dumps) and `supports_on_host=False`
  (same charter as mongo / phpmyadmin — shimkit doesn't manage
  host-installed Redis).

### Changed

- `stack lemp` rejects non-SQL backing DBs with a clearer error
  (mongo / redis / phpmyadmin can run alongside via the per-
  engine `shimkit db <engine> up` but don't fit the L-E-M-P role).
- `DbManager._EngineBound.up` plumbs `Engine.up_command` through
  to `docker run` via the new optional `command=` kwarg.

### Tests

- 16 new tests in `tests/test_tools_db_redis.py` (1070 → 1086
  total). Registry membership + insertion order, pure engine
  driver shape (environment_for_up empty / up_command argv /
  shell_argv with --no-auth-warning / no-password fallback /
  supports_dump=False / supports_on_host=False / data_dir /
  container_port), manager plumbing (up passes command= through
  docker.containers.run / dump refused / on-host refused),
  config defaults present.
- Adjusted two pre-existing tests that used `redis` as an "unknown
  engine" placeholder (now a valid name).

### Notes

`shimkit db redis up` gives Laravel / Symfony / Django users a
local Redis cache and queue backend without touching the host
package manager. Pairs with the framework recipes — set
`REDIS_URL=redis://default:shimkit-dev@127.0.0.1:16379/0` in
your `.env` / `.env.local` / `settings.py`.

Gates: pytest 1086 passed, ruff clean, mypy strict clean. No new
optional dependency extras.

## [0.14.0] — 2026-05-16

### Added

- `shimkit framework symfony` — sibling framework recipe under the
  existing `framework` parent. Four commands:
  - `perms PATH [--group G]` (MODERATE) — cross-distro group
    detection (same chain as Laravel: `getent` / `dscl` / `grp`);
    targets `var/` rather than Laravel's `storage` +
    `bootstrap/cache`.
  - `env PATH [--name N] [--env E] [--db D]` (MODERATE) —
    scaffolds `.env.local` with a generated `APP_SECRET`
    (hex(32) — Symfony's documented form). Refuses to overwrite
    an existing file. `DATABASE_URL` targets shimkit dev DBs
    by default; supports mysql / mariadb / postgres.
  - `cache-clear PATH [--env E]` — wraps `php bin/console
    cache:clear --env <env>`. Defaults to `dev`.
  - `console -- <args>` — passthrough to `php bin/console`. Host
    execution by default; `--in-container` routes through
    `shimkit stack lemp`.

  Symfony has no built-in scheduler like Laravel's
  `schedule:run`, so there's no `cron-install` command —
  application-specific cron entries go via `shimkit cron add`
  directly.

- `tools.framework.symfony` config block with the same shape as
  `tools.framework.laravel` plus a `default_env` field (`dev` /
  `test` / `prod`).

### Tests

- 26 new tests in `tests/test_tools_framework_symfony.py` (1044 →
  1070 total). Platform gating, perms (path refusal / dry-run /
  var/ targeting / chgrp skip on missing group / --group override
  / failed-step JSON output), env scaffold (overwrite refusal /
  APP_SECRET 64-hex-char shape / default APP_ENV / `--env`
  override / DATABASE_URL for all three DB engines including
  serverVersion query parameter / dry-run no-write / uniqueness
  across two scaffolds), console (host happy path runs `php
  bin/console` / missing-php exits 69 / no-args refusal / missing-
  bin/console refusal / --in-container delegates to StackManager),
  cache-clear (runs console with --env flag), command surface
  (framework --help lists symfony alongside laravel; symfony
  --help lists all four subcommands).

### Notes

Second framework recipe under the `framework` parent. Future
siblings (`rails`, `django`, `nextjs`) follow the same pattern.

Gates: pytest 1070 passed, ruff clean, mypy strict clean. No new
optional dependency extras.

## [0.13.0] — 2026-05-16

### Added

- `shimkit tls request --method dns-cloudflare` — DNS-01 ACME
  challenge via Cloudflare. Required for wildcard certs (`*.example.com`).
  Uses the upstream `certbot/dns-cloudflare:v3.0.1` image (auto-
  selected when `--method dns-cloudflare` is passed; the webroot
  method still uses `certbot/certbot:v3.0.1`).
- `--credentials PATH` flag on `tls request`. Points at a file
  containing `dns_cloudflare_api_token = <token>` (one line).
  Manager refuses the file when mode isn't 0600 — certbot also
  refuses, but shimkit catches it earlier with a clearer message.
  Parent directory of the file is mounted at `/credentials`
  inside the container read-only.
- `tools.tls.certbot_dns_cloudflare_image` config field — pin the
  DNS plugin image independently of the webroot image.
- `tools.tls.cloudflare_propagation_seconds` config field —
  default `60`, range `[0, 600]`. Lower it on accounts with fast
  Cloudflare propagation; raise for slow zones.

### Changed

- `_is_valid_domain` accepts a leading `*.` for wildcard domains
  (required by DNS-01). The rest of the domain validates as before.
- `tls request` `--webroot` is now optional — required for the
  webroot method but not for dns-cloudflare. The error message
  guides the user to the right flag combination for each method.
- `TlsConfig.default_method` widened from `Literal["webroot"]` to
  `Literal["webroot", "dns-cloudflare"]`.

### Tests

- 17 new tests in `tests/test_tools_tls_dns_cloudflare.py` (1027 →
  1044 total). Pure argv-builder shape (DNS flags + propagation +
  staging/dry-run combos; webroot path unaffected), container_volumes
  with + without credentials mount, manager validation
  (missing-credentials refusal / missing-file refusal / loose-mode
  refusal / happy path picks dns-cloudflare image and mounts
  credentials parent dir / JSON output includes method), config
  plumbing (cloudflare_propagation_seconds range validation).

### Notes

DNS-01 is the only ACME path that supports wildcard certs. The
plugin image is ~70MB so the first `tls request --method
dns-cloudflare` pulls it; subsequent runs are local.

Cloudflare-only today. Other DNS providers (Route53,
DigitalOcean, etc.) each need their own credential surface — opt-
in extras in a future release.

Gates: pytest 1044 passed, ruff clean, mypy strict clean. No new
optional dependency extras (reuses `[docker-clean]`'s `docker`).

## [0.12.0] — 2026-05-15

### Changed

- `docs/shipping-checklist.md` — refreshed to reflect post-v0.11.0
  state. Was stuck at v0.1.0 references; now tracks the current
  blockers (Phase 2.4 `pypi` GitHub Environment + Phase 4.1/4.2
  PyPI trusted-publisher) and marks completed items including
  v0.10.0's coverage push and v0.12.0's codecov + attestation
  additions. Phase 3 (Homebrew tap) explicitly marked abandoned.
- `docs/plans/known-issues.md` — removed two entries now resolved:
  the v0.2.0 "coverage gap to 85%" (hit in v0.10.0) and the
  "Optional: gh attestation verify smoke test" (added to
  release.yml in this release).
- `.design/plans/validation-report.md` — "Follow-up TODOs
  (post-v0.5.0)" rewritten as a closeout showing every item now
  shipped (cron → v0.6, framework laravel → v0.7, tls → v0.8,
  `--on-host` for db → v0.9, coverage → v0.10).
- `docs/README.md` Tools section — expanded from 5 listed tools to
  all 18 currently shipped, grouped into host tools / server-class
  (Docker-first) / framework recipes.

### Added

- `.github/workflows/ci.yml` uploads coverage to codecov.io
  (`codecov/codecov-action@v5`). Only the Ubuntu 3.12 cell uploads
  to avoid double-counting; OIDC token-less upload for public
  repos. Coverage floor raised from 65% to 80%.
- `.github/workflows/release.yml` `verify-attestation` job —
  downloads the published wheel + sdist after `github-release` and
  runs `gh attestation verify` against each. Catches a
  misconfiguration of the publish flow. Documented as optional in
  known-issues.md before v0.12.0; tracked there with a "low
  priority" tag.

### Notes

Doc-only release plus two small CI additions. No source code
changes. CI floor moved from 65% to 80% because we're at 85% line
coverage as of v0.10.0; 80% leaves margin for platform-gated test
skips on macOS / Python-version cells.

## [0.11.0] — 2026-05-15

### Added

- `docs/release-notes/v0.5.0.md` through `v0.10.0.md` — per-version
  user-facing release notes. Previously only v0.2.0 had one.
  v0.7.1 has a thin stub pointing at v0.7.0.
- `docs/release.md` — PyPI trusted-publisher setup section
  (one-time, by a maintainer with PyPI write access).

### Changed

- `.github/workflows/release.yml` — restored the `publish-pypi`
  job using `pypa/gh-action-pypi-publish` with OIDC trusted
  publishing. Runs in parallel with `github-release` after `build`
  so a PyPI outage doesn't block the GitHub Release. Stages
  wheel + sdist into `dist-pypi/` so the SBOM JSON (which PyPI
  rejects) stays out of the upload.
- `docs/architecture.md` — extended the `core/` directory listing
  with `docker.py`, `host_service.py`, `version.py` (added across
  v0.5-v0.9). Extended the `tools/` listing with the eight new
  tools shipped since v0.4. Added an "Adding a new tool" guidance
  block: which primitive to reach for by tool kind, sub-app
  parent convention (framework laravel, web nginx).
- `docs/README.md` — release-notes index lists v0.10 → v0.5.0
  newest-first plus the v0.7.1 patch.

### Notes

This is a **doc-only release**. No source code changes. PyPI
publishing for v0.11.0 itself requires the user to complete the
trusted-publisher setup on PyPI first (see `docs/release.md`);
the workflow will succeed for `github-release` and fail at
`publish-pypi` with `invalid-publisher` otherwise.

## [0.10.0] — 2026-05-15

### Tests

- Coverage push from 74% to **85%** (1009 → 1027 tests added across
  11 new test files; +397 tests on top of the v0.9.0 baseline).
  All new tests target previously-thin code paths in:
  - `core/` — command (sudo/has_sudo/CommandResult), platform
    (WSL detection, brew-prefix, container probes), menu
    (FallbackMenu fallback paths + Menu.prompt_for_change),
    host_service (SystemdHost + BrewServicesHost), systemd
    (state / lifecycle / journal), ui (banner / spinner / quiet).
  - `tools/java/` — manager menu paths (_menu_install /
    _menu_upgrade / _menu_switch / _menu_uninstall /
    _menu_remove_oracle / run() loop), scanner (scan / homebrew
    versions / SDKman / JAVA_HOME), installer (install /
    reinstall / uninstall / upgrade / switch / verify /
    reload_env), brew (prefix cache / install / outdated / link),
    oracle (safe-roots enforcement).
  - `tools/ssh/` — manager (keys_generate / keys_rotate / agent
    paths / known_hosts audit + prune / perms audit + fix /
    config show / run() loop), scanner (parse_agent_keys / 
    parse_known_hosts / prune_known_hosts / list_keys / 
    _looks_like_private_key / _read_pub_metadata).
  - `tools/adguard/` — manager (scan with/without conflicts /
    verify / loopback DNS / ports_show / ports_set / service /
    logs / rollback / config_validate), ports (psutil branch +
    cgroup parsing).
  - `tools/dns/` — manager (diagnose / flush / show / test /
    set / reset / fix dispatcher / no-service paths), fixer
    (detect_interference / step_detect_vpn / _make_backup_dir
    safety / latest_backup_dir / rollback).
  - `tools/db/` — _to_status_row helper, --on-host JSON output
    paths, on-host Linux + macOS service-name resolution, dump
    to file, status JSON shape with running container.
  - `tools/gpg/` — manager (keys_generate / keys_export /
    git_signing_show / git_signing_configure / agent_status /
    run() loop), error paths for missing git binary.
  - `tools/docker_clean/` — manager (prune dispatch / quick
    dry-run / nuke token enforcement / inspect / compose_down
    with/without --volumes / schedule_emit stdout vs file).
  - `tools/tls/` — revoke dry-run, renew failure exit-code
    propagation, status with unparseable expiry, cron-install
    delegation.
  - `tools/hosts/` — _read_source URL + local file paths,
    _back_up sudo failure + success, _atomic_write fallback
    chain, run() interactive loop.
  - `tools/web/nginx/` — list with empty sites-available, apply
    + remove severe-token enforcement, vhost generate flavors.
  - `cli.py` — config show/path/edit/validate, doctor full run,
    self-update no-update path, per-tool --help registration.

### Changed

- `pyproject.toml` — added `tests/* = ["RUF012"]` to ruff's
  `per-file-ignores`. Test stubs use throwaway classes to mock
  pydantic models; RUF012 (mutable class-attribute defaults
  need ClassVar) is real-code advice that doesn't apply to
  dataclass-style test fakes.

## [0.9.0] — 2026-05-15

### Added

- `shimkit db <engine> ... --on-host` — opt-out from container-
  first. When `--on-host` is passed, `up` / `down` / `status` /
  `shell` route through `HostService` (systemd on Linux, `brew
  services` on macOS) and manage an already-installed host
  engine rather than a container. Available for mysql / mariadb
  / postgres; mongo and phpmyadmin are intentionally
  container-only (mongo's host-packaging surface is messy;
  phpmyadmin has no host install).

  **shimkit does NOT install packages in --on-host mode** — if
  the engine's client (`mysql`/`mariadb`/`psql`) isn't on PATH,
  the command refuses with a clear remediation. This is the
  redesign's core safety promise: the original ubuntu scripts
  had five Critical security flags from install-on-host
  patterns (0.0.0.0 binds, deprecated apt-key, curl|sh) and
  shimkit's `--on-host` mode explicitly avoids reproducing
  them.

- `shimkit.core.HostService` — new abstraction with
  `SystemdHost` (Linux) and `BrewServicesHost` (macOS) concrete
  backends. `HostService.detect(platform)` returns the right
  one or `None` for unsupported systems. Exposes `state()` /
  `start()` / `stop()` returning a typed `HostServiceResult`.
  Pairs with the existing `Systemd` facade — the new class is
  the cross-platform layer above it.

- `tools.db.host_services` config block — per-engine service-
  name mapping for Linux + macOS. Defaults: `mysql` →
  `mysql` (both), `mariadb` → `mariadb` (both), `postgres` →
  `postgresql` on Linux / `postgresql@16` on macOS. Override
  per-install in user config when your distro or homebrew
  formula diverges.

- `Engine.supports_on_host()` / `Engine.host_shell_argv()` /
  `Engine.host_client_binary()` — three new methods on the
  engine ABC. Mysql / mariadb / postgres override
  `supports_on_host=True` and provide host-side argv targeting
  `127.0.0.1`; mongo / phpmyadmin keep the default `False`.

### Changed

- `DbManager.boot(on_host=True)` — skips the docker preflight
  entirely when the caller is using `--on-host`. Container-mode
  methods now assert `self._env is not None` at entry; this
  prevents a stray `up()` call on an on-host manager from
  blowing up with `AttributeError` on a None DockerEnv.

### Tests

- 21 new tests in `tests/test_tools_db_on_host.py` (609 → 630
  total). Boot semantics (on_host skips docker preflight;
  default still runs it), refusals (mongo / phpmyadmin /
  missing-binary / unsupported-platform), up / down / status
  happy paths on both Linux and macOS service-name resolution,
  dry-run no-op, failed start propagates exit 1, shell
  routes through CommandRunner with PGPASSWORD for postgres,
  engine driver layer correctness.

## [0.8.0] — 2026-05-15

### Added

- `shimkit tls` — TLS cert lifecycle helper via container-first
  certbot. Six commands: `request -d D [-d D2 ...] --email E
  --webroot PATH [--staging]` (MODERATE — issuance via webroot
  ACME challenge); `list [--json]` and `status DOMAIN [--json]`
  (read-only enumeration with expiry parsing); `renew [-d
  DOMAIN] [--force-renewal]` (MODERATE — defaults to all due);
  `revoke -d DOMAIN --confirm REVOKE-TLS` (SEVERE); `cron-install
  [--schedule S]` (MODERATE — installs daily `shimkit tls renew`
  via `shimkit cron`). Replaces the ubuntu/ source script's
  ad-hoc letsencrypt setup with a container-first lifecycle.
  Persists `/etc/letsencrypt/` state at
  `~/.shimkit/data/tls/etc-letsencrypt/` so account + cert
  history survive container exits. Default image
  `certbot/certbot:v3.0.1` (pinned, configurable). Cert expiry
  parsed by shelling out to host `openssl x509 -enddate`;
  `tools.versions.openssl` floor at `1.1`. Adds 48 tests (561 →
  609 total). One of the deferred v0.5+ candidates from the
  ubuntu migration's validation report. No new optional
  dependency extras (reuses `[docker-clean]`'s `docker` package).
  [`docs/tools/tls.md`](docs/tools/tls.md).

### Changed

- `core/docker.DockerEnv` gains `run_oneshot(image, command,
  ...)` — detached-then-waited container run that captures exit
  code + stdout + stderr and auto-removes the container on exit.
  Used by `shimkit tls` for certbot invocations; available to
  any future tool that needs one-shot container semantics.
- `core/version.py` registers an `openssl` detector (parses both
  `OpenSSL` and `LibreSSL` version strings — macOS ships
  LibreSSL by default).

## [0.7.1] — 2026-05-15

### Fixed

- Release-workflow drift: the v0.7.0 tag was pushed with
  `pyproject.toml` still at `0.6.0` (only `src/shimkit/__init__.py`
  got bumped). The release workflow's tag-version verifier
  rejected the mismatch and v0.7.0 never published. v0.7.1 bumps
  both files to the same value and re-issues the v0.7.0 surface
  unchanged. No code or test changes.

## [0.7.0] — 2026-05-15

### Added

- `shimkit framework laravel` — Laravel-specific helpers under a
  new `framework` parent sub-app (future siblings: `symfony`,
  `rails`, `django`, `nextjs`). Four commands: `perms PATH
  [--group G]` (MODERATE — cross-distro group detection via
  `getent` on Linux, `dscl` on macOS; chgrp skipped when the group
  doesn't exist on the host); `env PATH [--name N] [--env E] [--db
  D]` (MODERATE — scaffolds `.env` with a generated `APP_KEY`,
  default DB settings target `shimkit db` containers, refuses to
  overwrite an existing file); `cron-install PATH` (MODERATE —
  wraps `shimkit cron add` with the Laravel-shaped `php artisan
  schedule:run` invocation); `artisan -- <args>` (host execution
  by default, `--in-container` routes through `shimkit stack
  lemp`). Replaces the legacy `add:laravel-perms.sh` and laravel-
  flavored `add:cron.sh` scripts. Adds `php` to the version
  detector registry (`tools.versions.php`, default min `8.1`).
  Adds 33 tests (561 total) and `cwd` to the `CommandRunner.run`
  chokepoint.
  [`docs/tools/framework-laravel.md`](docs/tools/framework-laravel.md).

## [0.6.0] — 2026-05-15

### Added

- `shimkit cron` — generic user-crontab editor. `show` / `list` /
  `add --name N --schedule S --cmd C [--comment T]` (MODERATE
  prompt) / `remove NAME` (MODERATE) / `rollback` (MODERATE).
  Shimkit-managed entries identified by a `# shimkit:<name>`
  comment immediately above the schedule line; user-authored
  entries never touched. Atomic write via `crontab <tempfile>`;
  backup-on-mutate to `~/.shimkit/data/cron/crontab-YYYY...bak`.
  Structural schedule validation (5-field or `@`-shorthand); cron
  itself owns semantic validation. Adds 25 tests (528 total). No
  new optional dependency extras. Replaces the source ubuntu
  `add:cron.sh` (which was Laravel-specific); shimkit cron is the
  generic host-side editor any framework can layer on.
  [`docs/tools/cron.md`](docs/tools/cron.md).

## [0.5.0] — 2026-05-15

### Migration

Migrated the legacy `ubuntu/` server-provisioning scripts into
shimkit under a **Docker-first** charter expansion. The original
22-script tree (LEMP installer, mysql/mariadb/postgres/mongo
host-installers, nginx vhost generator, supervisor / cron / laravel
helpers) had 5 Critical + 7 High security flags — disabled apparmor,
mongodb/mysql bound to `0.0.0.0`, deprecated `apt-key adv`,
`curl|sh` patterns. The Docker-first design dissolves every
Critical without per-tool effort.

Full audit + gap analysis + plan under
[`.design/`](.design/) (architecture-current, architecture-target,
version-constraints-spec, plans/feature-gap-analysis,
plans/migration-plan).

### Added

- **`shimkit.core.version`** — tool-version detection + constraint
  enforcement subsystem. One source of truth (the JSON
  `tools.versions` registry) consulted at three enforcement points
  (install-time docs, runtime preflight, `shimkit doctor`) with
  four distinct outcomes (OK / OUT_OF_RANGE / MISSING /
  UNPARSEABLE). Five built-in detectors: docker / nginx / git /
  gpg / python. SemVer-aware comparison via
  `packaging.SpecifierSet` — no home-rolled parser. Adds 35
  tests. Full spec:
  [`.design/version-constraints-spec.md`](.design/version-constraints-spec.md).
- **`shimkit.core.docker.DockerEnv`** — shimkit-flavored chokepoint
  for the docker-py SDK. Builder pattern; boot-checks the daemon
  once; standardises container naming
  (`shimkit-<scope>-<kind>-<id>`) and volume layout
  (`~/.shimkit/data/db/<engine>-<id>/`). Containers shimkit creates
  carry a `shimkit.tool=<scope>` label. Adds `network_get_or_create`
  + `network_remove` for the multi-container stack recipes. Adds
  28 tests (mocked at the SDK boundary; no real daemon access).
- **`shimkit db <engine>`** — container-first databases. Five
  engines (mysql / mariadb / postgres / mongo / phpmyadmin)
  registered via the per-engine driver pattern under
  `tools/db/engines/`. Subcommands: `ls`, `up` (idempotent —
  already-running, started-from-stopped, or fresh), `down`,
  `shell` (engine-native client), `dump` (mysqldump / pg_dumpall /
  mongodump --archive), `reset` (SEVERE — `--confirm RESET-DB`),
  `status` / `--json`. Default ports shimkit-prefixed
  (`:13306` / `:13307` / `:15432` / `:17017` / `:18080`); default
  bind 127.0.0.1; persistent volume at
  `~/.shimkit/data/db/<engine>-<id>/`. phpmyadmin links to a
  backing DB via `host.docker.internal`. Adds 35 tests.
- **`shimkit web nginx vhost`** — hardened vhost generator with
  opt-in apply. `generate` writes a file (no host mutation by
  default; `--out PATH` or stdout); `apply` and `remove` are
  SEVERE-tier (`--confirm APPLY-VHOST` / `--confirm
  REMOVE-VHOST`), refuse to clobber non-shimkit-managed vhosts via
  a `# managed-by: shimkit` marker check. Three flavors: static /
  php / laravel. Security headers borrowed from the source
  ubuntu `nginx:host.sh` (X-Frame-Options, X-Content-Type-Options,
  X-XSS-Protection, Referrer-Policy, `server_tokens off`) plus
  modern additions (Permissions-Policy). Adds 21 tests.
- **`shimkit stack lemp`** — three-container LEMP recipe. db
  (mysql/mariadb/postgres via the W3 engine drivers) + php-fpm
  + nginx, all on a per-project user-defined bridge network so
  containers can fastcgi-pass each other by name. Project root
  bind-mounted at `/srv/app`. Idempotent `up` (already_running /
  started / created per role); `down` removes all three + the
  network; `status` / `logs` / `exec` round out the surface.
  Multiple projects side-by-side via `--project`. Adds 21 tests.
- **`shimkit shell colors`** — 256-color ANSI palette diagnostic.
  Read-only; prints the basic 16 + 6x6x6 cube + 24-step grayscale
  ramp. `--json` returns the structured Xterm-RGB dump. Adds 7
  tests.

### Changed

- **`shimkit doctor`** extended with a `versions` section that
  tabulates the status of every detector in the version registry
  with platform-specific remediation hints (`brew install …` on
  macOS; `apt-get install …` on Linux).
- **`shimkit docker-clean` and `shimkit gpg git-signing` managers**
  now consult the version-constraint registry on boot, so a
  missing or out-of-range docker / git surfaces the same
  structured remediation message as the new tools. `--force` is
  plumbed through to override an `OUT_OF_RANGE` for docker-clean.

### Removed

- The legacy `ubuntu/` source tree is removed in a separate W9
  commit (after the validation report is approved). Archived at
  `.design/archive/ubuntu-snapshot-YYYYMMDD.tar.gz` (SHA-256
  recorded in `.design/plans/validation-report.md`). The migration
  skipped 15 source features — including the entire host-install
  path for php / node / composer / packages, the Laravel-specific
  scaffolders, supervisor + cron helpers, and three
  broken/duplicate scripts. See
  [`.design/plans/feature-gap-analysis.md`](.design/plans/feature-gap-analysis.md).

## [0.4.0] — 2026-05-15

Three more host-machine dev-workflow tools, same five-rule
architecture, same MODERATE-prompt-on-mutators pattern (where
applicable). Test count 295 → 351. No new optional dependency
extras.

### Added

- `shimkit logs` — system log tail / grep. macOS routes through
  `log show` / `log stream` (Apple's Unified Logging); Linux
  routes through `journalctl`. Read-only by design — no
  mutators, no prompts. Per-platform predicate syntax passed
  through verbatim (NSPredicate on macOS, journalctl flags on
  Linux). `--json` short-circuits the shell-out and emits the
  argv list that would run, useful for previewing flag
  combinations. Adds 14 tests.
  [`docs/tools/logs.md`](docs/tools/logs.md).
- `shimkit gpg` — GPG key + git-signing hygiene. `keys
  list/generate/export`, `agent status`, `git-signing
  show/configure [--scope global|local]`. Shells out to baseline
  `gpg` + `git`; passphrases stay in gpg's TTY pinentry (never
  captured by shimkit). Pure parser for `gpg --with-colons` (algo
  IDs → friendly names; unix-epoch timestamps → ISO dates;
  `expires=0` → `None`). `git-signing configure` writes exactly
  two `git config` entries (`user.signingkey`,
  `commit.gpgsign=true`) via `CommandRunner` to respect Rule 2.
  Adds 20 tests (337 total). [`docs/tools/gpg.md`](docs/tools/gpg.md).
- `shimkit env` — `.env` viewer + scaffolder with default-deny
  secret redaction. `show [PATH] [--reveal]`, `list [ROOT]`,
  `scaffold PATH`, `diff A B`, `redact SRC DST`. Default-deny on
  values: keys matching the secret-fragment regex (same shape as
  `core/log.py::redact_value`) are masked as `KEY=********`
  until `--reveal` is passed. Pure parser handles `KEY=value`,
  `KEY="quoted"`, `KEY='single'`, `export KEY=...`, trailing
  comments. Variable interpolation (`${OTHER}`) deliberately not
  supported — that's a runtime concern. Auto-discovers a `.env`
  in cwd via `tools.env.default_search_paths`. Adds 22 tests (339
  total): parser unit tests including escape decoding, secret
  pattern matcher, redact value capping, scaffold refusal on
  overwrite, list pruning of `node_modules`/hidden dirs. No new
  optional dependency extras. [`docs/tools/env.md`](docs/tools/env.md).

## [0.3.0] — 2026-05-15

Three new host-machine dev-workflow tools, each shipped under the
existing five architecture rules (CommandRunner chokepoint, UI
chokepoint, config-driven values, builder pattern, fluent self).
Test count 252 → 295. No new optional dependency extras — all
three use only baseline binaries that ship with the OS.

### Added

- `shimkit ssh` — SSH key + agent + known_hosts + perms hygiene.
  `keys list/generate/rotate`, `agent status/add`,
  `known-hosts audit/prune`, `perms audit/fix`, `config show
  [HOST]`. No third-party deps; passphrases stay in `ssh-keygen`'s
  TTY prompt (never logged or captured). Permission matrix is
  config-driven (`tools.ssh.perms`); audit flags only laxer-than-
  expected modes — stricter modes pass. 23 tests covering scanner
  units (list_keys / parse_agent_keys /
  find_known_host_duplicates / audit_perms), every CLI subcommand,
  dry-run no-op assertions, and the moderate-prompt refusal under
  `--no-input`. [`docs/tools/ssh.md`](docs/tools/ssh.md).
- `shimkit ports` — cross-platform TCP/UDP port owner inspector +
  killer. `shimkit ports show [PORT]` lists every listening socket
  via `lsof` on macOS or `ss` on Linux; `shimkit ports kill PORT`
  signals the holder(s) with a MODERATE prompt. Allowed signals
  `TERM/KILL/INT/HUP`; system-tier PIDs (below
  `tools.ports.system_pid_threshold`, default 100) require the
  severe-tier `--confirm KILL-INIT` token. No new optional extras —
  uses `CommandRunner` only. Adds 19 tests (parser fixtures for
  both `lsof -F pcnuP` and `ss -tulnpH` output, plus CLI/manager
  coverage). [`docs/tools/ports.md`](docs/tools/ports.md).
- `shimkit hosts` — `/etc/hosts` editor with atomic-write +
  timestamped backups. `show`, `add IP NAME`, `remove NAME`,
  `block DOMAIN` / `unblock DOMAIN` aliases, `apply-list SOURCE`
  (SEVERE — `--confirm APPLY-LIST`), `rollback`. Pure parser
  (`editor.py`) is text-in/model-out and unit-testable; manager
  follows the same `sudo install` → bind-mount-fallback pattern
  as `adguard.resolv.write_resolv_static`. URL fetch via stdlib
  `urllib.request` — no extra deps. Adds 20 tests (parser
  round-trip, IP validator, idempotent add, severe-token gate,
  cap enforcement, rollback restore).
  [`docs/tools/hosts.md`](docs/tools/hosts.md).

## [0.2.3] — 2026-05-14

### Removed

- Container image as a release channel. Docker was a testing
  artifact during development (used by the `adguard-mutating-
  integration` CI job, which pulls a third-party systemd-capable
  image, not ours). The brief's documented install methods are uv /
  pipx / brew / pip — Docker was never one of them. Removed:
  `Dockerfile`, `publish-ghcr` workflow job, `dockerfile-hadolint`
  CI job, Dependabot's `docker` ecosystem entry, the Dockerfile
  checklist row in the PR template. The existing
  `ghcr.io/simtabi/shimkit:0.2.x` image is left in place but won't
  be updated by future tags.
- `publish-pypi` and `bump-homebrew-tap` jobs (deferred). v0.2.2's
  `publish-pypi` repeatedly failed with `invalid-publisher` even
  with trusted-publishing configured on pypi.org. Restoration
  path: [`docs/shipping-checklist.md`](docs/shipping-checklist.md)
  Phase 4.

### Changed

- `docs/installation.md` leads with the GitHub-Release wheel +
  `pip install git+...@tag`; PyPI-style commands are marked
  pending. `docs/release.md`, `docs/shipping-checklist.md`,
  `docs/validation-scope.md`, `docs/onboarding.md`,
  `docs/plans/known-issues.md`, and `prompt.md` updated to drop
  `publish-ghcr` / `dockerfile-hadolint` / Dockerfile references.

## [0.2.2] — 2026-05-14

### Fixed

- Release pipeline: trusted-publishing now configured on PyPI for
  this repo + workflow + `pypi` environment, so `publish-pypi` can
  exchange its OIDC token for an upload credential. v0.2.1 published
  the container to GHCR and the GitHub Release but failed at the
  PyPI step with `invalid-publisher`. Also carries the release.yml
  `contents: write` grant on the `publish-ghcr` job so the container
  SBOM lands on the Release page instead of erroring with "Resource
  not accessible by integration".
- **Code is byte-identical to v0.2.1 (and v0.2.0); the bump is
  purely a release-infra retry to land the artifact on PyPI.**

## [0.2.1] — 2026-05-14

### Fixed

- Release pipeline: `actions/attest-build-provenance` requires
  either a public repo or a paid org plan; the v0.2.0 build job
  failed at the attestation step so nothing reached PyPI. Repo
  flipped to `public` (matches the Simtabi OSS default) and
  `release.yml` gained a `workflow_dispatch` trigger for future
  retries without force-pushing tags. **Code at v0.2.1 is
  identical to v0.2.0; the bump is purely a release-infra
  retry.**

## [0.2.0] — 2026-05-14 (unpublished)

### Added

- `shimkit dns` — macOS DNS resolver recovery. Ports `fixdns.sh` with
  the BSD-grep, Wi-Fi-only, `timeout(1)`, and bash 3.2 spinner bugs
  fixed. Commands: `diagnose`, `flush`, `show`, `set`, `reset` (token),
  `test`, `profile list`, `fix` (6-step escalation with optional
  nuclear via `--confirm REGENERATE`), `rollback`,
  `diagnostics export`.
- `shimkit adguard` — AdGuard Home port-conflict fixer for Linux.
  Ports `fix-adguardhome-ports.sh` with the run-without-AGH, awk-yaml,
  NetworkManager-warning-only, and yaml-while-AGH-running bugs fixed.
  Prefers the HTTP control API; falls back to ruamel.yaml edits after
  stopping AGH. Commands: `scan`, `fix` (with `--dns-cleanup-only`,
  `--remap-only`, `--migrate-from-pihole`), `verify`, `ports
  show|set`, `config validate`, `service start|stop|restart|status`,
  `logs`, `rollback`.
- `shimkit docker-clean` — Docker resource cleanup for Linux + macOS +
  WSL. Ports `docker-nucker.sh` with the `local x=$(...); if [ $? -eq
  0 ]` always-success bug, `((var++))` set-e abort, and missing-named-
  buildx-builder bugs fixed. Uses the docker-py SDK; `docker desktop
  restart` for Docker Desktop 4.37+. Commands: `status`, `quick`,
  `nuke` (`--confirm DELETE`), `restart`, `stop-all`, `prune-images`,
  `prune-volumes`, `prune-networks`, `prune-builders`, `orphans`,
  `inspect`, `compose-down`, `schedule` (emit only — no install).
- Core: `shimkit.core.log` (stdlib logging with JSONL `--log-file`,
  with redaction of secret-looking keys), `shimkit.core.json_event`
  (typed `Event` for `--json` mode), `shimkit.core.systemd` (typed
  systemctl wrapper used by `adguard` and `docker-clean`),
  `shimkit.core.cli_flags` (shared Typer `Option` defaults used by
  every new subcommand for uniform `--dry-run`, `--json`, `--quiet`,
  `--verbose`, `--log-file`, `--timeout`, `--yes`).
- `UI.line` and `UI.set_quiet` — plain-output primitive plus a quiet
  mode that suppresses everything except `UI.error`.
- CI: new `security` job (bandit + pip-audit), `dockerfile-hadolint`,
  `build` (sdist+wheel artifact), `smoke` (install built wheel on
  macOS + Ubuntu and run the CLI). Pytest now runs with `--cov` and
  a **65%** coverage floor — **233 tests** at HEAD (the original 77
  plus 38 for the three new tools plus 101 follow-up tests targeting
  manager methods, fixer steps, pruner error paths, resolv mutators,
  api set_ports payload, desktop fallback, and the parsers in
  scutil/networksetup/client/yaml_editor/cgroup-v2, plus 11 from the
  cleanup-2026-05-14 pass covering CLI-flag wiring, MODERATE prompts,
  extras-missing exit 69, and EX_CONFIG exit 78). Per-tool
  coverage: dns 76% (scutil 96%, commands 93%), adguard 64%
  (yaml_editor 97%, finder 88%), docker_clean 73% (models 97%,
  schedule 86%). Raising toward 85% as additional tests land —
  remaining gaps are mostly in the interactive `run()` menus and
  the most destructive paths (nuclear plist reset, resolv mutators
  on real `/etc/*`), validated by Phase 7 manual smoke instead.
- CI: new `adguard-integration` job pinned to AGH v0.107.74. Downloads
  the upstream binary on ubuntu-latest, runs it on non-default ports
  (5300/8000) so it doesn't collide with the runner's
  systemd-resolved, pre-bakes a yaml with a bcrypt-hashed throwaway
  user, and exercises `shimkit adguard scan/verify/ports show/fix
  --dry-run/ports set --dry-run` against the live daemon. JSON output
  asserted; AGH log captured on failure. Closes the "v0.2.0 needs a
  real-Linux integration run" gap.
- ruff config: `extend-immutable-calls = ["typer.Argument",
  "typer.Option"]` so B008 stops false-positiving on Typer's API.

### Changed

- `cli.py` no longer calls `typer.echo` / `typer.secho` / `subprocess`
  directly. Every output path goes through `UI.*`; the `$EDITOR`
  launch in `config edit` goes through `CommandRunner.run(...,
  capture_output=False)`. `shimkit doctor` extended with `dns`,
  `adguard`, and `docker` probes.
- `shimkit adguard verify`, `adguard ports show`, `adguard ports set`,
  and `adguard config validate` now accept `--install PATH` (matching
  `adguard scan`/`adguard fix`). The flag overrides the auto-detected
  install path so non-root callers (CI, dev sandboxes) can point at
  an AGH instance outside the default candidate paths.
- `Brew.install_self` (Homebrew bootstrap) no longer interpolates the
  config-supplied URL into a shell command. URL is validated as HTTPS,
  downloaded to a tempfile, then executed via `/bin/bash <tmpfile>`.

### Security

- `bandit` and `pip-audit` are now CI gates. All `# nosec`
  suppressions have one-line justifications at the suppression site.
- `pkgmgr.PackageManager` templates now accept an argv-list form
  (preferred, no shell). `defaults.json` ships with argv lists for
  every PM. The legacy string-template form is kept for backward
  compatibility with existing user configs.
- `Brew.install_self` no longer interpolates a config URL into a
  shell command. It downloads to a tempfile (HTTPS scheme validated)
  and executes via `/bin/bash <tmpfile>` without shell.
- `dns.fixer._make_backup_dir` refuses paths outside `$HOME` or
  `/tmp`, so a malicious config can't redirect plist backups to
  `/etc`.
- `core.command` exports `is_root()` and `has_sudo_cached()`;
  `AdGuardManager.boot(require_root=True)` (used by `adguard fix`
  outside `--dry-run`) refuses to proceed without elevation.
- `Dockerfile` base image pinned by manifest digest
  (`python:3.12-slim@sha256:401f6e1a...`). Dependabot's `docker`
  ecosystem watches the line; new digests come in as reviewable PRs.

### Removed

- The `installer/` directory (`install.sh` and the Homebrew formula
  template). The custom `curl | sh` installer is no longer
  shipped — installation goes through the direct package-manager
  channels (`uv tool install shimkit` / `pipx install shimkit` /
  `pip install --user shimkit` / `brew install simtabi/tap/shimkit`).
  Side effects:
  - `installer-shellcheck` CI job removed.
  - `release.yml`'s install.sh + install.sh.sha256 asset upload
    steps removed; SBOM is still uploaded to the GitHub Release.
  - `self_update.install_one_liner()` renamed to `install_commands()`
    and now returns the list of direct install commands rather
    than the curl-pipe URL.
  - README, `docs/installation.md`, `docs/release.md`,
    `docs/release-notes/v0.2.0.md`, `docs/validation-scope.md`,
    `prompt.md`, `SECURITY.md`, and the PR template scrubbed of
    install.sh references.

### Added (post the initial Unreleased section, in commit order)

- `scripts/test_adguard_mutating.sh` and the
  `adguard-mutating-integration` CI job: run the real
  `shimkit adguard fix` (and `ports set` yaml fallback) inside a
  privileged systemd container with `systemd-resolved` AND
  NetworkManager active. Asserts the drop-in path, the
  resolv.conf rewrite, the NM `dns=none` drop-in, and the
  AGH-stop-edit-start dance. Covers six of the seven Phase 7
  manual items; only the real-link-event check remains manual.
- `docs/plans/known-issues.md`: documents the one Phase 7 check
  that cannot be automated (real NetworkManager link-event
  survival on a real desktop), why containers can't validate it,
  and the manual procedure for release-time verification.
- `docs/plans/cleanup-2026-05-14.md`: end-of-session audit of
  gaps between shipped docs and shipped code (notably:
  partially-wired CLI flags, missing MODERATE-tier prompts, test
  coverage of CLI plumbing). Cleanup plan included.
- Shared CLI flags now wired through every new tool's Typer
  callback: `--quiet`, `--verbose`, `--log-file`, `--no-color`,
  `--color {auto,always,never}`, `--no-input`. Previously declared
  in `core/cli_flags.py` but only some commands consumed them;
  the rest silently dropped the flag.
- `Menu.prompt_for_change()` and `UI.set_no_input()` /
  `UI.set_color_mode()` so MODERATE-tier confirmations can be
  short-circuited by `--yes` / `--force` and skipped under
  `--no-input` (returns refusal rather than blocking).
  `shimkit dns set`, `shimkit adguard ports set`, and the
  `shimkit docker-clean prune-*` family now use this — the brief
  promised MODERATE prompts but no command implemented them.
- Test coverage: `--quiet`, `--verbose`, `--log-file`,
  `--no-color`, `--color`, `--no-input` exercised at the
  app-callback level; MODERATE-tier prompt exercised on
  `shimkit dns set`; extras-missing → exit 69 exercised on both
  `adguard` and `docker-clean` (sabotaging `psutil` and `docker`
  imports). Closes the brief's "mandatory minimum" gap.
- `tests/conftest.py` autouse fixture resets `UI._quiet` /
  `_color_override` / `_no_input` and the log file-handler state
  between tests so a flag-setting test doesn't bleed into the
  next.

### Fixed (post the initial Unreleased section)

- `Systemd.write_drop_in` accepts an optional `target_dir=` kwarg;
  `adguard.disable_resolved_stub()` now writes to
  `/etc/systemd/resolved.conf.d/` (the `[Resolve]` config dir),
  not `/etc/systemd/systemd-resolved.service.d/` (service-unit
  override dir, which systemd-resolved silently ignores for
  `[Resolve]`-section directives). **This bug silently disabled
  the entire "disable stub listener" feature on every real run
  prior to v0.2.0** — the drop-in landed in the wrong directory
  and systemd-resolved kept holding port 53.
- `adguard.write_resolv_symlink()`, `write_resolv_static()`,
  `configure_network_manager()` now return `bool` indicating
  whether the operation actually succeeded. `manager.fix()`
  aggregates these honestly: `outcome.applied = True` only when
  every sub-step succeeded; `outcome.error` is set on failure.
  Previously the orchestrator unconditionally claimed success
  even when sub-steps silently failed.
- `manager.fix()` notes now reflect what actually happened per
  step. Previously the "NetworkManager dns=none drop-in written"
  note was emitted regardless of whether NM was active —
  misleading users on headless servers without NM installed.
- `write_resolv_static()` falls back to a Python direct-write
  through the existing inode when `sudo install` fails. Handles
  the Docker bind-mounted `/etc/resolv.conf` case without
  breaking the atomic-replace path on real hosts.
- `adguard yaml_editor.read_ports()` now reads `http.address`
  ("host:port") as the canonical AGH 0.107.x form for the web UI
  port; falls back to legacy `http.port`. `set_ports()` writes
  `http.address` and updates `http.port` if present in the file
  for consistency. AGH's schema-version-34 migration drops
  `http.port` and keeps `http.address`; the previous read path
  reported the wrong port after AGH's first config rewrite.
- `cli.py::doctor()` docker probe shells out to `docker version
  --format '{{.Server.Version}}'` via `CommandRunner` instead of
  going through the docker-py SDK. Avoids a lingering Unix-socket
  fd that triggered pytest's UnraisableException warning on
  Python 3.12+ and failed the next-running test.
- `cli.py::config edit` no longer imports `subprocess` directly;
  the `$EDITOR` launch goes through `CommandRunner.run(...,
  capture_output=False)` (Rule 2 compliance).
- `tools/adguard/ports._pid_to_unit()` accepts an injectable
  `proc_root=` parameter; the test no longer subclasses `Path`
  (which broke on Python 3.12+ when pathlib internals changed
  `_parts` → `_raw_paths`).
- `shimkit adguard rollback` now accepts `--install PATH` for
  consistency with the other `adguard` subcommands.
- `mypy strict` no longer false-positives on optional-extra
  modules (`ruamel.yaml`, `requests`, `psutil`, `docker`,
  `dnspython`) via `[[tool.mypy.overrides]]` in `pyproject.toml`.
  CI installs `[dev]` only by default; without the override,
  every type-check matrix cell failed with `import-not-found`.
- `pip-audit` in CI now runs without `--strict`. The combination
  of `--strict` and `--skip-editable` was a footgun: the latter
  was meant to silently skip the editable shimkit install, but
  the former promoted the skip notice to a hard error.
- `hadolint` in CI now ignores `DL3013` (pin pip versions) in
  addition to `DL3008`. We deliberately want the latest pip in
  the build stage.
- `[dev]` extras now include `ruamel.yaml`, `requests`, `psutil`,
  `docker`, and `dnspython` so the test matrix doesn't fail with
  `ModuleNotFoundError` when running the new tool tests.
- `adguard-integration` CI job's wait-loop curl now passes Basic
  auth (`ADGUARD_USER` / `ADGUARD_PASS`). With `users:` populated
  in the pre-baked yaml, AGH gates `/control/status` behind
  auth — an unauthenticated curl gets 401 and `-f` makes the loop
  time out even when AGH is healthy.
- `UI._color_enabled()` is resilient to a broken config: previous
  code called `get_config().ui.color`, which re-raised
  `ConfigError` when validation failed — the very `UI.error()`
  call meant to explain the problem then crashed with a secondary
  exception, leaving the user with a Python traceback instead of
  the config error. UI now falls back to TTY auto-detect when
  `get_config()` fails.
- `shimkit config validate` now exits **78** (EX_CONFIG, from
  `sysexits.h`) on validation failure, distinct from generic exit
  1. Scripts can detect "config is broken" specifically. Previously
  documented in the brief but never wired.

## [0.1.0] — Initial release

shimkit is a toolkit of developer utilities — Python tools, shimmed by
bash.

### Tools

- `shimkit java` — OpenJDK version manager: install / list / switch /
  upgrade / uninstall / remove-oracle. Supports macOS (Apple Silicon +
  Intel), Linux, WSL, and container environments. Interactive menu
  when called bare; scriptable subcommands otherwise.
- `shimkit shell` — Shell upgrader for bash / zsh / fish / ksh via
  whichever package manager the host provides (brew, apt, dnf, yum,
  pacman, apk, zypper). Warns before upgrading the currently active
  shell; `--force` to skip the prompt.
- `shimkit config` — Inspect, edit, and validate user configuration.
- `shimkit doctor` — System diagnostics (platform, shell, package
  manager, brew presence, config validity, install method).
- `shimkit self-update` — Detects how shimkit was installed
  (uv / pipx / brew / pip) and dispatches to the matching upgrade
  command. Queries PyPI for the latest version.

### Architecture

- Single `CommandRunner` chokepoint for every subprocess invocation.
- Cross-platform primitives in `shimkit.core`: Platform, Shell,
  ShellConfigWriter, PackageManager, UI (NO_COLOR-aware), Menu
  (questionary + stdin fallback).
- Layered JSON config with pydantic v2 schema, strict-mode key
  validation, auto-generated JSON Schema for editor autocomplete.
  Precedence: bundled defaults → `~/.config/shimkit/shimkit.json` →
  `$SHIMKIT_CONFIG` → `NO_COLOR`.
- Builder-pattern orchestrators: `Tool.create().boot().run()`.
- Fluent return-self contracts on UI, Shell, ShellConfigWriter.

### Distribution

- Installable via uv (`uv tool install shimkit`), pipx
  (`pipx install shimkit`), pip (`pip install --user shimkit`), or a
  Homebrew tap (`brew install simtabi/tap/shimkit`).
- One-liner installer hosted on GitHub Releases:

  ```bash
  curl -fsSL --proto '=https' --tlsv1.2 \
    https://github.com/simtabi/shimkit/releases/latest/download/install.sh \
    | sh
  ```

- PEP 561 `py.typed` marker — downstream consumers get full type
  hints. mypy strict + ruff + pytest run on CI for macOS + Ubuntu ×
  Python 3.10–3.13.

### Compatibility

- Python ≥ 3.10. macOS and Linux (including WSL, Docker, LXC,
  Kubernetes). Windows requires WSL.

[0.1.0]: https://github.com/simtabi/shimkit/releases/tag/v0.1.0

Copyright © 2026 [Simtabi LLC](https://simtabi.com). MIT licensed.
