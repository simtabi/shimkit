# Migration plan — `ubuntu/` → shimkit v0.5.0

> Phase 3 deliverable. Ordered, atomic work items. Stop & review
> before implementation per the task spec's checkpoint cadence.

Dependencies:
`W1` → `W2` → `{W3, W4}` → `W5` → `W6` → `W7` → `W8` → `W9`.
`W3` and `W4` can be done in parallel (different package trees).

## W1 — Version-constraints subsystem ▶ must-have

**Scope:** Implement `core/version.py` (detector registry, status
enum, validate / preflight / validate_all). Add `VersionConstraint`
to `config/schema.py` and a `tools.versions` block in
`defaults.json` covering the tools shimkit *already* needs (docker,
git, gpg, nginx, python). Extend `shimkit doctor` to call
`validate_all()` and tabulate.

**Files:**

- new `src/shimkit/core/version.py`
- edit `src/shimkit/core/__init__.py` (re-export)
- edit `src/shimkit/config/schema.py` (`VersionConstraint`,
  `VersionsConfig`)
- edit `src/shimkit/config/defaults.json` (`tools.versions` block)
- edit `src/shimkit/cli.py::doctor` (call `validate_all()`)
- new `tests/test_core_version.py` (~30 tests)

**Tests:** parsers per detector (offline fixtures of real CLI
outputs), constraint matrix, preflight exit-code mapping,
`shimkit doctor --json` shape.

**Rollback strategy:** isolated module; revert the single commit
removes everything.

**Acceptance criteria:**
- `shimkit doctor` shows a versions table.
- `shimkit doctor --json` includes `data.versions[*].status`.
- Calling `version.preflight(("docker",))` from a manager exits 69
  with a remediation message when docker is missing or out-of-range.
- mypy strict, ruff, bandit clean.

## W2 — `core/docker.py` ▶ must-have

**Scope:** Shimkit-flavored `DockerEnv` helper. Builder pattern.
Owns the docker-SDK chokepoint for the new tools. Standardises
container/volume naming. Wraps `find / run / start / stop / remove
/ exec / logs / volumes` with idempotency.

**Files:**

- new `src/shimkit/core/docker.py`
- edit `src/shimkit/core/__init__.py` (re-export `DockerEnv`)
- new `tests/test_core_docker.py` (~20 tests, all mocked at the
  docker-SDK boundary)

**Tests:** boot exits 69 when daemon unreachable; `find()` returns
None for non-existent name; `run()` ↔ `start()` choice based on
existing-state; container-name + volume-path helpers.

**Rollback strategy:** single new file + a re-export line; revert
both.

**Acceptance criteria:**
- `DockerEnv.create().boot()` returns Self on success, exits 69
  on daemon-down.
- Container naming convention: `shimkit-{scope}-{kind}-{id}`.
- Volume path convention: `~/.shimkit/data/db/{engine}-{id}/`.
- Zero direct calls to `docker.from_env()` outside this module
  (assertable via `grep`).
- mypy strict, ruff, bandit clean.

## W3 — `shimkit db` (engine framework + 5 engines) ▶ must-have

**Scope:** New `tools/db/` package. `DbManager` orchestrates. One
file per engine under `engines/`. Each engine declares image, port,
env, shell-cmd, dump-cmd. Subcommands: `ls`, `up`, `down`, `shell`,
`dump`, `reset` (SEVERE), `status`.

**Files:**

- new `src/shimkit/tools/db/__init__.py`
- new `src/shimkit/tools/db/commands.py` (Typer dispatcher)
- new `src/shimkit/tools/db/manager.py`
- new `src/shimkit/tools/db/models.py`
- new `src/shimkit/tools/db/engines/{__init__,base,mysql,mariadb,postgres,mongo,phpmyadmin}.py`
- edit `src/shimkit/config/schema.py` (`DbConfig`, `DbEngineEntry`)
- edit `src/shimkit/config/defaults.json` (`tools.db` block)
- edit `src/shimkit/cli.py` (`app.add_typer(db_app)`)
- new `tests/test_tools_db.py` (~40 tests across all 5 engines)
- new `docs/tools/db.md`

**Tests:**
- engine registry (`for_engine("mysql")` returns the right driver)
- `up` idempotency (already-running container is a no-op)
- `up` creates container with the right image, port binding, env
- `down` stops and removes
- `shell` builds the right argv for `docker exec`
- `dump` argv for each engine (mysqldump / pg_dump / mongodump)
- `reset` refuses without the SEVERE token
- `--json` for `status` and `ls`
- `--dry-run` makes zero docker-SDK calls
- `--no-input` refuses the MODERATE prompt
- platform / docker-missing exit 69

**Rollback strategy:** new package tree; revert.

**Acceptance criteria:** 5 engines, each with up/down/shell/dump
working under `--dry-run` test fixtures. `docs/tools/db.md`
written.

## W4 — `shimkit web nginx vhost` ▶ must-have

**Scope:** Hardened vhost generator. `generate` writes a file
(no host mutation by default). `--flavor {static,php,laravel}`
switches the template. `apply` and `remove` are SEVERE — gated
behind config-driven tokens. `list` reads
`/etc/nginx/sites-enabled/`.

**Files:**

- new `src/shimkit/tools/web/__init__.py`
- new `src/shimkit/tools/web/commands.py`
- new `src/shimkit/tools/web/nginx/__init__.py`
- new `src/shimkit/tools/web/nginx/commands.py`
- new `src/shimkit/tools/web/nginx/manager.py`
- new `src/shimkit/tools/web/nginx/templates.py` (Jinja-free; stdlib
  `string.Template`)
- edit `src/shimkit/config/schema.py` (`WebConfig`, `WebNginxConfig`)
- edit `src/shimkit/config/defaults.json` (`tools.web.nginx` block)
- edit `src/shimkit/cli.py` (`app.add_typer(web_app)`)
- new `tests/test_tools_web_nginx.py` (~25 tests)
- new `docs/tools/web.md`

**Tests:**
- 3 flavor outputs match expected fixture strings
- security headers present (X-Frame-Options, X-Content-Type-Options,
  Referrer-Policy, server_tokens off)
- `generate --out /tmp/...` writes the file
- `generate` (no --out) prints to stdout
- `apply` without `--confirm APPLY-VHOST` refuses with exit 1
- `apply` with token does atomic-write + reload (mocked)
- `remove` without token refuses
- `list` reads from a tmp `sites-enabled` dir
- `--no-input` refuses prompts

**Rollback strategy:** revert the package tree.

**Acceptance criteria:** generates valid nginx config that passes
`nginx -t` syntax check (executed in the CI smoke test where nginx
is installable).

## W5 — `shimkit stack lemp` ▶ must-have

**Scope:** Compose LEMP using the W3 engines + an nginx + php-fpm
container. `up` brings the whole stack live. Bind-mounts the cwd
at `/srv/app` in the php-fpm container. `down` stops + removes
all. `status` shows each piece. `logs` follows the lot. `exec`
runs in the php-fpm container.

**Files:**

- new `src/shimkit/tools/stack/__init__.py`
- new `src/shimkit/tools/stack/commands.py`
- new `src/shimkit/tools/stack/manager.py`
- new `src/shimkit/tools/stack/lemp.py`
- edit `src/shimkit/config/schema.py` (`StackConfig`, `LempConfig`)
- edit `src/shimkit/config/defaults.json` (`tools.stack` block)
- edit `src/shimkit/cli.py` (`app.add_typer(stack_app)`)
- new `tests/test_tools_stack.py` (~20 tests)
- new `docs/tools/stack.md`

**Tests:**
- `up --db mysql` creates 3 containers (db, php-fpm, nginx) with
  the configured naming.
- `up` is idempotent (already-up stack is a no-op).
- `down` removes all 3.
- `logs -f` exec'd against multiple containers in parallel.
- `exec <cmd>` runs in php-fpm (not nginx).
- `--dry-run` makes zero docker-SDK calls.

**Rollback strategy:** revert the package tree.

**Acceptance criteria:** `shimkit stack lemp up --dry-run` enumerates
exactly the 3 containers it would create.

## W6 — `shimkit shell colors` ▶ should-have

**Scope:** Small read-only diagnostic. Adds a `colors` subcommand
to the existing `shimkit shell` Typer app.

**Files:**

- new `src/shimkit/tools/shell/colors.py`
- edit `src/shimkit/tools/shell/commands.py` (register subcommand)
- new `tests/test_tools_shell_colors.py` (~5 tests)
- edit `docs/tools/shell.md` (`Colors` section)

**Acceptance criteria:** `shimkit shell colors` prints a 16-color
ANSI grid; `--json` returns the structured palette; UI chokepoint
respected.

## W7 — Wire constraint preflight into existing tools ▶ should-have

**Scope:** Drop `version.preflight((...))` one-liners into the
managers that newly depend on detected tools:

- `tools/docker_clean/manager.py` → `("docker",)`
- `tools/db/manager.py` → `("docker",)`
- `tools/stack/manager.py` → `("docker",)`
- `tools/web/nginx/manager.py` → `("nginx",)` only when `apply`
  is invoked (lazy)
- `tools/gpg/manager.py::git_signing_*` → `("git", "gpg")`

**Files:** edits only. No new files.

**Acceptance criteria:** removing `docker` from PATH and running
`shimkit docker-clean status` now exits 69 with a remediation
message sourced from `pkgmgr` (rather than the existing terse
"docker not found").

## W8 — Docs + CHANGELOG + README ▶ must-have

**Scope:**

- `docs/tools/{db,stack,web}.md` written during W3/W4/W5; verify ToC.
- README's tool list extended.
- `docs/installation.md` adds a "Version Requirements" section
  rendered from the constraints registry.
- `CHANGELOG.md` `[0.5.0]` block.
- `prompt.md` charter expansion note (Docker-first server tools).
- `docs/architecture.md` brief pointer to `.design/architecture-target.md`.

**Acceptance criteria:** README ToC matches the actual `docs/` tree.
`shimkit --help` lists 14 user commands (the 4 new + the existing 10
that were in 0.4.0).

## W9 — Validation gate + archive + delete ubuntu/

**Scope:** Phase 6 + Phase 7 of the task spec.

1. Run the full validation checklist; produce
   `.design/plans/validation-report.md`.
2. Open the PR. Wait for explicit user approval of the report.
3. On approval: `tar -czf .design/archive/ubuntu-snapshot-YYYYMMDD.tar.gz`
   the source dir, record SHA-256, verify the archive opens cleanly.
4. `rm -rf` the source.
5. Final commit: `chore: retire legacy ubuntu/ source after migration`.

**No file under `.design/plans/_workspace/` is referenced by code or
docs at this point.** The workspace dir gets cleaned in W9 too.

## Total scope estimate

| Phase | LOC | Tests |
|------:|----:|------:|
| W1 (version) | 350 | 30 |
| W2 (docker)  | 250 | 20 |
| W3 (db)      | 700 | 45 |
| W4 (web nginx)| 350 | 25 |
| W5 (stack lemp)| 350 | 22 |
| W6 (shell colors)| 80 | 6 |
| W7 (preflight wire-in) | 30 | 5 |
| W8 (docs)    | docs-only | n/a |
| W9 (archive + delete)  | n/a | n/a |
| **Total** | ≈ 2,110 | ≈ 153 (351 → 504) |

## Schedule shape

Sequential: W1, W2 (different packages, can be done in parallel by
the agent's standards — same engineer, separate commits).

Then W3 + W4 in parallel (W4 has no dependency on W3).

Then W5 (depends on W3's engines + W4's nginx template).

Then W6, W7 (independent, parallel).

Then W8 (docs across everything), then W9 (validate, archive,
delete).

If a work item slips, the cut point is "ship what's in"; W5/W6
are removable from v0.5.0 if needed (LEMP can be v0.5.1; `shell
colors` can be v0.5.2).

## Open risks

- **W1's `python` detector** vs. shimkit-itself: shimkit's own
  `pyproject.toml` declares `requires-python = ">=3.10"`. The
  in-config `tools.versions.python` constraint is currently
  declarative-only — at install time pip enforces it, at runtime
  it's tautological. We keep the constraint in the registry for
  symmetry with the other tools, and so `shimkit doctor` shows the
  user "yes you're on a supported python".
- **W3's mongo + mariadb** image-tag choices: MongoDB 7 changed
  licensing; some environments are stuck on 4.4 or 5.0 forks. Keep
  the image fully overridable in config (`tools.db.engines.mongo.image`).
- **W4's nginx vhost apply path** assumes a Debian/Ubuntu-style
  `/etc/nginx/sites-{available,enabled}` layout. RHEL-family uses
  `/etc/nginx/conf.d/` only. Add a config knob and detect at boot
  rather than hard-coding the Debian path.
- **W5's stack-lemp** combines containers from multiple images
  with bind-mounts; on macOS Docker Desktop's bind-mount perf is
  the well-known wart. Document; don't try to solve.
- **W9 deletion** of the source — `ubuntu/` is NOT in any git
  repository. The tarball in `.design/archive/` is the ONLY
  recovery path. Verify the archive twice (SHA recorded, archive
  manually opened) before `rm -rf`.

## Stop & review

The next message after this plan should be **your decision** on:

1. Approve the plan as-is and proceed to W1 implementation.
2. Approve the plan with edits (call them out).
3. Trim — pick a subset of W1..W6 to ship and defer the rest to v0.5.1.

Do **not** auto-proceed past this checkpoint without explicit
acknowledgement, per the task spec.
