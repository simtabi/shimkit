# Validation report — ubuntu → shimkit migration (v0.5.0)

> Phase 6 deliverable per the migration task spec. Gates Phase 7
> (archive + delete of the legacy `ubuntu/` source). **Do not
> proceed with deletion until this report is approved.**

Branch:   `feat/ubuntu-migration`
Head:     (filled in at commit time)
Date:     2026-05-15

## Checklist

- [x] **Full test suite green** — `pytest -q` reports
      `503 passed` (was 351 at v0.4.0; +152 across W1–W6).
- [x] **Linter clean** — `ruff check src tests` and
      `ruff format --check src tests` both pass.
- [x] **Type-check clean** — `mypy src` reports
      `Success: no issues found in 107 source files`.
- [x] **Security scan clean** — `bandit -r src/shimkit -ll`
      reports `Medium: 0, High: 0`.
- [x] **`shimkit doctor` runs successfully** — full output
      includes the new `versions` section with status + remediation
      hints for `docker / nginx / git / gpg / python`.
- [x] **Every Adopt-list feature has at least one test exercising
      it** — coverage matrix:

      | Adopt-list item              | Test module                       | Cases |
      |------------------------------|-----------------------------------|------:|
      | core/version (W1)            | `tests/test_core_version.py`       | 35 |
      | core/docker (W2)             | `tests/test_core_docker.py`        | 28 |
      | `shimkit db` (W3, 5 engines) | `tests/test_tools_db.py`           | 35 |
      | `shimkit web nginx` (W4)     | `tests/test_tools_web_nginx.py`    | 21 |
      | `shimkit stack lemp` (W5)    | `tests/test_tools_stack.py`        | 21 |
      | `shimkit shell colors` (W6)  | `tests/test_tools_shell_colors.py` | 12 |
      | **Total new**                |                                    | **152** |

- [x] **Every new public API is documented** —
      `docs/tools/db.md`, `docs/tools/web.md`, `docs/tools/stack.md`
      written; `docs/tools/shell.md` gained a "`shimkit shell
      colors`" section; `docs/installation.md` gained a "Version
      requirements" section; `docs/architecture.md` has a banner
      cross-linking the four `.design/` reference docs.
- [x] **README ToC matches the actual `docs/` tree** — 14 per-tool
      doc links in README; 14 `*.md` files in `docs/tools/`; diff
      shows perfect overlap.
- [x] **No file under `.design/plans/_workspace/` is referenced by
      code or docs** — grep across `src/`, `docs/`, `README.md`,
      `CHANGELOG.md` returns zero hits for `_workspace`. (The
      workspace dir's two files — `source-inventory.md` and
      `risk-flags.md` — are scratch artifacts for the Phase 1
      audit; they exist on disk under `.design/plans/_workspace/`
      and will be cleaned in W9 if the maintainer prefers, but
      they're not load-bearing.)
- [x] **`git status` is clean except for intended changes** —
      everything committed; tree clean before the validation
      report itself.
- [x] **Manual smoke test of two representative features** —

      1. `shimkit doctor` — runs on dev machine, prints the new
         `versions` table with every detector reporting `ok` against
         the live host's binaries (docker 28.5.2, nginx 1.27.2, git
         2.51.0, gpg 2.4.9, python 3.10.19).
      2. `shimkit shell colors --json` — emits the 256-cell palette
         dump; first three entries verify the `section` /
         `index` / `rgb` shape and that basic indices return
         `rgb=null` while cube/grayscale return RGB triples.

## Summary

### What was migrated (Adopt list)

Four new top-level commands plus two cross-cutting primitives, all
under the **Docker-first** charter expansion:

| Feature | Surface | Pre-migration source |
|---------|---------|----------------------|
| `core/version` | Tool-version detection + constraint enforcement | n/a (new) |
| `core/docker` | DockerEnv chokepoint for the docker-py SDK | n/a (new) |
| `shimkit db` | Container-first databases: mysql / mariadb / postgres / mongo / phpmyadmin. `ls / up / down / shell / dump / reset (SEVERE) / status` | `installers/database/install:{maria,mongo,mysql,postgres}.sh` + `installers/tools/install:phpmyadmin.sh` |
| `shimkit web nginx vhost` | Hardened generator with opt-in apply. 3 flavors (static / php / laravel). `generate / apply (SEVERE) / remove (SEVERE) / list` | `configurators/servers/nginx:host.sh` + `nginx:laravel.sh` |
| `shimkit stack lemp` | 3-container LEMP recipe (db + php-fpm + nginx). `up / down / status / logs / exec`. Multi-project via `--project` | `installers/stacks/install:lemp.sh` (5-line orchestrator) |
| `shimkit shell colors` | 256-color ANSI palette diagnostic | `assets/bash-colors.sh` (palette piece only; PS1 helpers skipped) |

### What was skipped (with reasons)

The audit's Skip list, copy-edited from
[`.design/plans/feature-gap-analysis.md`](feature-gap-analysis.md):

| Source | Reason |
|--------|--------|
| `install:certbot.sh` | TLS issuance design non-trivial under the Docker charter (DNS-01 vs HTTP-01); deferred to v0.6+. |
| `install:composer.sh` | Composer ships inside the LEMP php container; host install belongs to `brew` / `apt`. |
| `install:node.sh` | `nvm` / `volta` / `asdf` are industry standard; competing is a charter overreach. |
| `install:packages.sh` | Bulk apt installer is the antithesis of shimkit's per-tool design. |
| `install:php.sh` | Host PHP install is `shimkit stack lemp`'s job inside a container. |
| `install:php7.sh` | Broken (`apt install -packages/extentions-`); also obsolete name (installs PHP 8.0). |
| `install:server-env.sh` | Near-duplicate of `install:nginx.sh`; both redundant with `shimkit stack lemp`. |
| `configurators/aliases` | Alias curation is per-user dotfile territory. |
| `configs:supervisor.sh` | Supervisor is fading vs. container restart policies / systemd. |
| `add:cron.sh` | Laravel-specific shape; a generic `shimkit cron` is a v0.6+ candidate. |
| `create:mysql.sh` | Subsumed by `shimkit db mysql shell` + SQL. |
| `expressjs:setup.sh` | Too project-shaped (clones a repo, writes a systemd unit); not packagable. |
| `laravel:initialize.sh` | Too project-shaped; that's a `make` / Taskfile concern. |
| `laravel:file-perms.sh` | Niche Laravel-only; deferred to a future `shimkit framework laravel`. |
| Three legacy / dup trees (`__src/server-main`, `server-main 2`, `scripts/initializers/server-main`); the empty `scripts/security/` and `docs/` dirs | Empty / duplicate / legacy. |

### Security wins from the redesign

All 5 Critical and most 7 High flags from
[`.design/plans/_workspace/risk-flags.md`](_workspace/risk-flags.md)
dissolve under the Docker-first redesign:

- C1 (`service apparmor stop && teardown`) — N/A inside a
  container.
- C2 (MongoDB `bindIp: 0.0.0.0` + UFW 27017) — N/A; shimkit-managed
  mongo binds 127.0.0.1:17017 by default.
- C3 (MySQL grants `*.*` to `'%'` over network + `bind-address =
  *`) — N/A; shimkit-managed mysql binds 127.0.0.1:13306 by
  default.
- C4 (`apt-key adv --recv-keys`) — N/A; Docker official images
  don't need it.
- C5 (`curl ... | sudo bash`) — N/A; node lives inside the
  php/node official images.

### Follow-up TODOs (post-v0.5.0) — all shipped

Closeout note added in v0.12.0:

- ✅ **v0.6.0** `shimkit cron add/list/remove` — generic
  user-crontab editor. [Release notes](../../docs/release-notes/v0.6.0.md).
- ✅ **v0.7.0** / v0.7.1 `shimkit framework laravel` — `perms` /
  `env` / `cron-install` / `artisan`.
  [Release notes](../../docs/release-notes/v0.7.0.md).
- ✅ **v0.8.0** `shimkit tls / certbot` — webroot DNS-01 deferred
  to v0.13.0. [Release notes](../../docs/release-notes/v0.8.0.md).
- ✅ **v0.9.0** `--on-host` mode for `db`. Not for `stack` — that
  recipe is intrinsically multi-container.
  [Release notes](../../docs/release-notes/v0.9.0.md).
- ✅ **v0.10.0** Coverage push 74% → 85% (+397 tests).
  [Release notes](../../docs/release-notes/v0.10.0.md).

## Phase 7 plan (gated on approval)

When approved by the maintainer, W9 deletion proceeds as:

1. **Archive** the source: from a clean working tree,

   ```bash
   tar -czf .design/archive/ubuntu-snapshot-2026-05-15.tar.gz \
       -C /Users/imanimanyara/Artisan/projects/opensource/simtabi ubuntu/
   ```

   The archive is the **only** recovery path — `ubuntu/` is not in
   any git repository.

2. **Verify** the archive opens cleanly:

   ```bash
   tar -tzf .design/archive/ubuntu-snapshot-2026-05-15.tar.gz | wc -l
   # expect 89 (88 tracked files + the .DS_Store skipped earlier)
   shasum -a 256 .design/archive/ubuntu-snapshot-2026-05-15.tar.gz
   ```

   Record the SHA-256 in this report under "Archive details" before
   `rm -rf`.

3. **Delete** the source:

   ```bash
   rm -rf /Users/imanimanyara/Artisan/projects/opensource/simtabi/ubuntu
   ```

4. **Final commit** on the migration branch:

   `chore(w9): retire legacy ubuntu/ source after migration (archived in .design/archive/)`

5. **Open the PR** against `main` with this report + the migration
   plan in the description.

## Archive details

| | |
|---|---|
| Archive path     | `.design/archive/ubuntu-snapshot-2026-05-15.tar.gz` |
| SHA-256          | `3491cb8fe9ebd7250f608117679fb981410de9db7bd8e044bce6eee39715a367` |
| Size             | 35 KB (gzip) |
| File count       | 115 entries (88 files + 27 dirs/DS_Store entries) |
| Source size      | 416 KB (88 tracked files) |
| Verified         | `tar -tzf` parses; `tar -xzOf ... ubuntu/assets/bash-colors.sh` reads first lines of the palette script |
