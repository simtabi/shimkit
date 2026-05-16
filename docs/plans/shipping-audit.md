# Shipping audit — 2026-05-16

A comprehensive walk through every plan, design spec, and doc in
the repo. For each item: **what shipped**, **what's pending user
action**, **what's a permanent skip**, and **what's deferred to
demand-driven future work**.

The audit's job is to leave no item in any document silently
orphaned. If a plan said "we'll do X in v0.6+", this doc says
either "X shipped in v0.7.0" or "X is parked in
[future-additions.md](future-additions.md) until someone asks."

Cross-references:

- [`future-additions.md`](future-additions.md) — items captured
  with concrete patterns but no current demand.
- [`known-issues.md`](known-issues.md) — runtime checks that
  can't be containerised.
- [`../shipping-checklist.md`](../shipping-checklist.md) — the
  release-readiness operational checklist (different from this
  audit; that file tracks "ship readiness", this file tracks
  "feature completeness against plans").
- [`../../.design/plans/feature-gap-analysis.md`](../../.design/plans/feature-gap-analysis.md)
  — the original ubuntu/→shimkit Adopt/Skip/Improve/Defer
  matrix.
- [`../../.design/plans/validation-report.md`](../../.design/plans/validation-report.md)
  — v0.5.0 migration closeout report with its own follow-up
  list.

---

## A. Migration plan W1-W9 (ubuntu → shimkit, target v0.5.0)

Source: [`.design/plans/migration-plan.md`](../../.design/plans/migration-plan.md).

| W# | Deliverable | Shipped in | Notes |
|----|-------------|------------|-------|
| W1 | `core/version` — tool-version constraints | v0.5.0 | 5 detectors at v0.5; grew to 8 (+ php v0.7, openssl v0.8). |
| W2 | `core/docker.DockerEnv` chokepoint | v0.5.0 | Gained `run_oneshot()` in v0.8.0 + `command=` plumbing for Redis in v0.15.0. |
| W3 | `shimkit db` (5 engines) | v0.5.0 | 6 engines after redis (v0.15). + `--on-host` for SQL engines (v0.9). |
| W4 | `shimkit web nginx vhost` | v0.5.0 | — |
| W5 | `shimkit stack lemp` | v0.5.0 | + LEMP-backing-DB validation when redis joined registry (v0.15). |
| W6 | `shimkit shell colors` | v0.5.0 | — |
| W7 | docker-clean + gpg version preflight | v0.5.0 | — |
| W8 | Docs catchup | v0.5.0 | — |
| W9 | Archive + delete ubuntu/ source | v0.5.0 | SHA-256 recorded in validation-report.md. |

**Status: 9/9 complete.**

---

## B. Feature-gap-analysis Defer list (post-v0.5.0)

Source: [`.design/plans/feature-gap-analysis.md`](../../.design/plans/feature-gap-analysis.md)
"Decisions deferred to v0.5.x+".

| Item | Shipped in | Notes |
|------|------------|-------|
| `shimkit cron add/list/remove` (generic) | v0.6.0 | Replaced the Laravel-specific `add:cron.sh` source. |
| `shimkit framework laravel` | v0.7.0 / v0.7.1 | v0.7.1 was a version-drift recovery; surface unchanged. |
| `shimkit tls / certbot` | v0.8.0 (webroot) | DNS-01 added in v0.13.0 (Cloudflare) + v0.17.0 (Route53). |
| `--on-host` mode for db | v0.9.0 | mysql / mariadb / postgres only. mongo + phpmyadmin intentionally not supported (mongo's host packaging is messy; phpmyadmin has no host install). |
| `--on-host` mode for stack | **rejected** | Captured in [`future-additions.md`](future-additions.md) with rationale: stack lemp is intrinsically multi-container; the original ubuntu host-LEMP scripts had 5 Critical security flags. |

**Status: 4/4 deferred items shipped; 1/1 rejected with documented reasoning.**

---

## C. Validation-report follow-up TODOs (post-v0.5.0)

Source: [`.design/plans/validation-report.md`](../../.design/plans/validation-report.md).
Original list rewritten as a closeout in v0.12.0.

| TODO | Shipped in |
|------|------------|
| Coverage push toward 85% | v0.10.0 (74% → 85%, +397 tests) |
| All four Defer-list items | covered in B above |

**Status: closeout complete.**

---

## D. Cleanup-2026-05-14 deferred items

Source: [`docs/plans/cleanup-2026-05-14.md`](cleanup-2026-05-14.md).

| Item | Shipped in |
|------|------------|
| P2.3 — coverage push to 85% | v0.10.0 |
| P3.2 — `gh attestation verify` smoke | v0.12.0 |

**Status: 2/2 complete.** Manual-only NM check (P1.5 / Phase 7 item 7) stays in [`known-issues.md`](known-issues.md) by design — see section F.

---

## E. Shipping-checklist phases

Source: [`../shipping-checklist.md`](../shipping-checklist.md).

| Phase | Item | Status |
|-------|------|--------|
| 1.1-1.7 | Code/repo setup | ✅ done |
| **1.8** | **Branch protection on `main`** | **⏳ pending — user action; see section G** |
| 2.1-2.3 | GitHub remote setup | ✅ done |
| **2.4** | **`pypi` GitHub Environment** | **⏳ pending — user action; see section G** |
| 3 | Homebrew tap | 🗑 abandoned — see [`../shipping-checklist.md`](../shipping-checklist.md) Phase 3 |
| **4.1** | **PyPI account + 2FA** | **⏳ pending — user action; see section G** |
| **4.2** | **Configure PyPI trusted publisher** | **⏳ pending — user action; see section G** |
| 4.3 | TestPyPI (dry-run) | ⏸ optional |
| 5 | First PyPI upload | ▶ auto (blocked on 2.4 + 4.1 + 4.2) |
| 6 | Post-release / ongoing | ▶ auto |
| 7.1 | Coverage upload | ✅ done (v0.12.0, codecov.io) |
| 7.2 | Per-tool docs | ✅ done |
| 7.3 | mkdocs site | ⏸ optional |
| 7.4 | CITATION.cff | ⏸ optional |
| 7.5 | gh attestation verify smoke | ✅ done (v0.12.0) |

**Status: 4 user-side actions remain; everything in scope for code is shipped.**

---

## F. Permanent / out-of-charter (won't ship)

Documented decisions to **never** build, with rationale. Each has a
durable home in the repo:

### NM `dns=none` real-link-event check

Source: [`docs/plans/known-issues.md`](known-issues.md).

**Why permanent**: containers don't generate real network link
events, so we cannot validate that NetworkManager respects the
`dns=none` drop-in across a real interface state change inside CI.
The property is **upstream NetworkManager behaviour**, not shimkit
behaviour. NM has shipped `dns=none` since 2015 with their own
test coverage. If NM regresses, every DNS-manager tool (pi-hole,
AGH-CLI, Unbound's resolvconf integration) breaks together.

**Mitigation**: `shimkit doctor` surfaces NM service state, so a
user investigating flaky DNS post-fix can confirm in one command
whether NM is the active manager. Manual verification procedure
documented in `known-issues.md`.

### Ubuntu Skip list (15 items)

Source: [`.design/plans/feature-gap-analysis.md`](../../.design/plans/feature-gap-analysis.md)
**Skip** column.

| Item | Reason |
|------|--------|
| `install:composer.sh` | Ships in the LEMP php container; host install belongs to `brew` / `apt`. |
| `install:node.sh` | `nvm` / `volta` / `asdf` are industry standard. |
| `install:packages.sh` | Bulk-apt is the antithesis of shimkit's per-tool design. |
| `install:php.sh` | Host PHP install is `shimkit stack lemp`'s job inside a container. |
| `install:php7.sh` | Broken in source (literal `apt install -packages/extentions-`). |
| `install:server-env.sh` | Near-duplicate of `install:nginx.sh`. |
| `configurators/aliases/aliases` | Alias curation is per-user dotfile territory. |
| `configs:supervisor.sh` | Supervisor is fading vs container restart policies / systemd. |
| `database/create:mysql.sh` | `shimkit db mysql shell` + SQL covers this. |
| `expressjs:setup.sh` | Too project-shaped (clones repo, writes systemd unit). |
| `laravel:initialize.sh` | Too project-shaped — that's a `make` / Taskfile concern. |
| Three legacy/dup trees (`__src/server-main/`, `server-main 2/`, `scripts/initializers/server-main/`) | Duplicates of paths shimkit doesn't need. |
| `scripts/security/`, `docs/` (empty) | No content to migrate. |
| `scripts/help.sh` | Replaced by `shimkit --help` / per-tool `--help`. |
| `assets/bash-colors.sh` PS1 helpers | Dotfile territory; only the palette printer ported (v0.5.0 `shimkit shell colors`). |

**Status: 15/15 documented permanent skips.**

---

## G. User-side actions — pending, not deferrals

Two items in the repo state need the **user** to act (the
maintainer, via the GitHub / PyPI web UIs). These are blocked on
the human; shimkit's code is ready. They are **not deferrals**
and they don't belong in `future-additions.md` — they belong
here.

### G.1 — PyPI trusted-publisher config

**Why it matters**: Releases v0.11.0 through v0.18.0 all ran the
restored `publish-pypi` job, and all of them failed at the
`invalid-publisher` step because the user-side trusted-publisher
config isn't done yet. The wheel + sdist are live on the GitHub
Release page for every version; PyPI is empty.

**What needs to happen**:

1. **PyPI side** — log in to <https://pypi.org/manage/account/publishing/>
   and add a pending publisher with these EXACT values:

   | Field | Value |
   |-------|-------|
   | PyPI Project Name | `shimkit` |
   | Owner | `simtabi` |
   | Repository name | `shimkit` |
   | Workflow filename | `release.yml` |
   | Environment name | `pypi` |

2. **GitHub side** — `simtabi/shimkit` → Settings → Environments
   → "New environment" named `pypi`. No secrets required; OIDC
   provides credentials at runtime. Optionally add a Required
   Reviewer rule if you want a human gate before each upload.

3. **Retroactive uploads** — once both above are done, every
   failed `publish-pypi` job from v0.11.0 onward can be re-run:

   ```
   gh run list --workflow=release.yml | grep failure
   # for each failed run id:
   gh run rerun <run-id> --failed
   ```

   The wheel + sdist artifacts are still attached to each
   release (the `build` + `github-release` jobs succeeded);
   re-running picks up the existing build artifacts and only
   retries the upload step.

**Effort**: ~10 minutes for the maintainer with PyPI write access.

### G.2 — Branch protection on `main`

**Why it matters**: shimkit's CI catches issues (test failures,
lint, mypy strict), but nothing currently prevents a push to
`main` that bypasses CI entirely. With branch protection,
incoming PRs and direct pushes must pass the named status checks
before landing.

**What needs to happen**:

`simtabi/shimkit` → Settings → Branches → "Add rule" with:

- Branch name pattern: `main`
- ✓ Require status checks to pass before merging:
  - `test (macos-latest, 3.10)` through `test (ubuntu-latest, 3.13)` — the 8 matrix cells
  - `security`
  - `build`
  - `smoke (macos-latest)` + `smoke (ubuntu-latest)`
- ✓ Require branches to be up to date before merging
- (Optionally) ✓ Require a pull request before merging — flips the workflow to PR-based instead of direct-to-main

**Effort**: ~3 minutes for the maintainer.

---

## H. Demand-driven future additions

Captured separately in [`future-additions.md`](future-additions.md):

- More TLS DNS-01 providers (DigitalOcean, Hurricane Electric,
  Google Cloud DNS, Linode, OVH)
- More framework recipes (Rails, Next.js, Flask)
- More db engines (valkey, elasticsearch, opensearch, kafka,
  minio, clickhouse)

Each entry includes the concrete pattern + LOC estimate. The
graduation rule: build when someone asks. Naïve expansion turns
each `shimkit <tool>` boot into a Typer cold-start tax.

---

## I. Releases shipped this session

For reference / chronology:

```
v0.6.0    shimkit cron
v0.7.0    shimkit framework laravel
v0.7.1    fix version drift in pyproject.toml
v0.8.0    shimkit tls (webroot)
v0.9.0    shimkit db --on-host (mysql/mariadb/postgres)
v0.10.0   coverage 74% → 85%
v0.11.0   release-notes consolidation + PyPI workflow restored
v0.12.0   stale-doc cleanup + codecov + attestation-verify
v0.13.0   shimkit tls --method dns-cloudflare
v0.14.0   shimkit framework symfony
v0.15.0   shimkit db redis (sixth engine)
v0.16.0   shimkit framework django
v0.17.0   shimkit tls --method dns-route53
v0.18.0   post-v0.17 doc-sync
```

13 releases. Test count 561 → 1130. Coverage 74% → 85%. Every
gate green on every release (excluding `publish-pypi` —
section G.1).

---

## J. Audit conclusion

| Bucket | Count | Status |
|--------|-------|--------|
| Migration W-items (A) | 9 | ✅ shipped |
| Defer-list items (B) | 4 + 1 rejected | ✅ resolved |
| Validation-report TODOs (C) | 5 | ✅ shipped |
| Cleanup deferrals (D) | 2 | ✅ shipped |
| Shipping-checklist (E) — in-code | all | ✅ shipped |
| Shipping-checklist (E) — user-action | 2 | ⏳ pending (section G) |
| Shipping-checklist (E) — optional | 3 | ⏸ available if wanted |
| Permanent skips (F) | 16 | 🚫 documented |
| Future additions (H) | 14 | 📋 captured in `future-additions.md` |

**The plans tree is drained.** No item in any plan, design spec,
or doc is silently orphaned. Items either:

1. Shipped (and have a corresponding release-notes entry +
   CHANGELOG line).
2. Are blocked on a user action (this doc, section G).
3. Were explicitly rejected with rationale (this doc, section F).
4. Are parked for future demand (`future-additions.md`).

The next maintainer can read this doc and know exactly which
of those four buckets every documented intent ended up in.
