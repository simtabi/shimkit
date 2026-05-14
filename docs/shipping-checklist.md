# Shipping checklist

Everything that needs to happen between "code is ready" and "users can
`pip install shimkit`". Items are listed in **dependency order** —
later items assume earlier ones are done.

Three columns:

- **Status** — `done` (already in place), `pending` (someone needs
  to act), or `optional`.
- **Owner** — `code` (already shipped in the repo), `user` (you, via
  web UI or local terminal), or `ci` (the release workflow does it
  automatically when triggered).
- **Item** — what needs doing, with the exact command or click path.

Inputs that block downstream items are marked **⚠ blocker** in the
notes column.

For what each automated and manual gate validates (and what we
intentionally don't validate), see
[`validation-scope.md`](validation-scope.md).

---

## Phase 1 · Code & repo setup

| # | Status | Owner | Item |
|---|--------|-------|------|
| 1.1 | ✅ done | code | shimkit package built: src/ layout, hatchling backend, py.typed, bundled `defaults.json`. Wheel builds cleanly (`python -m build`). |
| 1.2 | ✅ done | code | Tests pass: 115 pytest cases (was 77; +38 for the new tools and the pkgmgr argv regression). ruff strict, mypy strict + pydantic plugin, shellcheck, bandit (`-ll`, fail on medium+), pip-audit (`--skip-editable`). |
| 1.3 | ✅ done | code | CI workflow — macOS + Ubuntu × Python 3.10/3.11/3.12/3.13. Jobs: `test`, `security` (bandit + pip-audit), `dockerfile-hadolint`, `build` (sdist+wheel artifact), `smoke` (install wheel in clean venv on macOS + Ubuntu and run `shimkit doctor`), `adguard-integration` (runs real AGH v0.107.74 on ubuntu-latest, exercises `scan/verify/ports show/fix --dry-run/ports set --dry-run` against a live daemon on non-default ports 5300/8000). |
| 1.4 | ✅ done | code | Release workflow — `guard` (validates tag == pyproject == `__version__` + CHANGELOG section present) → `build` (sdist+wheel, install.sh.sha256, SPDX SBOM, `actions/attest-build-provenance` for wheel + sdist) → `publish-pypi` (OIDC) → `github-release` (assets + SBOM) → `publish-ghcr` (multi-arch + attest-build-provenance to GHCR + container SBOM) → `bump-homebrew-tap`. |
| 1.5 | ✅ done | code | Container image: multi-stage, non-root `shimkit` user, OCI labels, `HEALTHCHECK ["shimkit", "version"]`, base image pinned by manifest digest (`python:3.12-slim@sha256:401f6e1a…`). `.dockerignore` present. Dependabot's `docker` ecosystem keeps the digest current. |
| 1.6 | ✅ done | code | Org-style docs: `README.md`, `docs/{installation,configuration,architecture,release,tools/{java,shell,dns,adguard,docker-clean}}.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`. |
| 1.7 | ✅ done | code | Community hygiene: `.github/ISSUE_TEMPLATE/{bug_report,feature_request,config}.yml`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/dependabot.yml` (pip + github-actions + docker, weekly Monday 06:00 America/New_York), `.pre-commit-config.yaml`. |
| 1.8 | ⏳ pending | user | Configure branch protection on `main`: require `test`, `security`, `build`, `smoke`, `dockerfile-hadolint` checks before merge. Repo Settings → Branches → Add rule. |

## Phase 2 · GitHub remote

| # | Status | Owner | Item |
|---|--------|-------|------|
| 2.1 | ✅ done | user | Repo exists at `simtabi/shimkit`. Default branch `main`. Initial commit pushed. |
| 2.2 | ✅ done | user | Repo metadata set: description, homepage, 10 topics (cli, python, java, jdk, openjdk, shell, homebrew, developer-tools, version-manager, dotfiles). Issues + Discussions enabled. |
| 2.3 | ✅ done | user | Local git identity scoped to noreply (`19682005+imanimanyara@users.noreply.github.com`) so future commits don't trip GH email privacy. |
| 2.4 | ✅ done | user | `pypi` GitHub Environment created in the repo (no protection rules — `wait_timer` needs paid plan for private repos). |
| 2.5 | ⏳ **pending** | **user** | **Make `simtabi/shimkit` public.** ⚠ blocker for install one-liner — the script lives at `releases/latest/download/install.sh` which 404s for anon users while the repo is private. |
|  |  |  | `gh repo edit simtabi/shimkit --visibility public --accept-visibility-change-consequences` |
| 2.6 | ⏸ optional | user | Add protection rules to the `pypi` environment once the repo is public (`wait_timer: 5`, required reviewers). Free on public repos. |

## Phase 3 · Homebrew tap

| # | Status | Owner | Item |
|---|--------|-------|------|
| 3.1 | ✅ done | user | `simtabi/homebrew-tap` repo created (public). Scaffolded with `README.md` + empty `Formula/` dir + initial commit. |
| 3.2 | ⏳ **pending** | **user** | **Create the `TAP_GITHUB_TOKEN` secret.** ⚠ blocker for the formula auto-bump step in `release.yml`. |
|  |  |  | 1. Generate a fine-grained PAT at <https://github.com/settings/tokens?type=beta>. |
|  |  |  | 2. **Repository access**: select **only** `simtabi/homebrew-tap`. |
|  |  |  | 3. **Permissions → Repository → Contents**: Read and write. |
|  |  |  | 4. **Permissions → Repository → Pull requests**: Read and write. |
|  |  |  | 5. **Expiration**: 90 days (set a calendar reminder to rotate). |
|  |  |  | 6. Copy the token, then in `simtabi/shimkit` → Settings → Secrets and variables → Actions → New repository secret, name = `TAP_GITHUB_TOKEN`, paste. |

## Phase 4 · PyPI

> **Deferred as of 2026-05-14.** The `publish-pypi` and
> `bump-homebrew-tap` jobs were removed from `release.yml` because
> PyPI's trusted-publisher configuration could not be made to match
> the GitHub OIDC claims for this repo (see `invalid-publisher` log
> in the v0.2.2 release run). Container + GitHub Release wheel are
> the distribution channels today. To re-enable, restore the jobs
> from git history and complete the items below.

| # | Status | Owner | Item |
|---|--------|-------|------|
| 4.1 | ⏸ deferred | user | **Register / sign in to PyPI** and enable 2FA. <https://pypi.org/account/register/>. |
| 4.2 | ⏸ deferred | user | **Configure the trusted publisher** for `shimkit`. <https://pypi.org/manage/account/publishing/> → Add a new pending publisher → GitHub. Fill in EXACTLY: |
|  |  |  | • PyPI Project Name: `shimkit` |
|  |  |  | • Owner: `simtabi` |
|  |  |  | • Repository name: `shimkit` |
|  |  |  | • Workflow name: `release.yml` |
|  |  |  | • Environment name: `pypi` |
| 4.3 | ⏸ optional | user | (Dry-run only) Configure a `testpypi` trusted publisher at <https://test.pypi.org/manage/account/publishing/> and a `testpypi` GitHub environment if you want to rehearse a release on TestPyPI before hitting real PyPI. |

## Phase 5 · First release

Prerequisites: 2.5 (public), 3.2 (tap token), 4.2 (PyPI publisher) all done.

| # | Status | Owner | Item |
|---|--------|-------|------|
| 5.1 | ⏳ pending | user | Confirm `pyproject.toml::project.version` and `src/shimkit/__init__.py::__version__` are the version you intend to ship. Currently both `0.1.0`. |
| 5.2 | ⏳ pending | user | Move `[Unreleased]` section in `CHANGELOG.md` to `[X.Y.Z] — YYYY-MM-DD`. (For 0.1.0, the section is already named `[0.1.0] — Initial release` — just add the date if you want.) |
| 5.3 | ⏳ pending | user | Cut the tag: `git tag v0.1.0 && git push origin v0.1.0` |
| 5.4 | ▶︎ auto | ci | `release.yml` runs: `guard` (tag-vs-version check) → `build` (sdist + wheel) → in parallel: `publish-pypi` (OIDC), `github-release` (assets), `publish-ghcr` (multi-arch container), `bump-homebrew-tap` (formula bump). |
| 5.5 | ⏳ pending | user | Verify the release (commands in [`docs/release.md`](release.md#verifying-a-release)). |

## Phase 6 · Post-release / ongoing

| # | Status | Owner | Item |
|---|--------|-------|------|
| 6.1 | ▶︎ auto | ci | **Dependabot** opens weekly PRs for pip / GitHub Actions / Docker base-image updates. Configured in [`.github/dependabot.yml`](../.github/dependabot.yml). |
| 6.2 | ⏳ pending | user | Rotate `TAP_GITHUB_TOKEN` before its 90-day expiry (set a reminder at the time of creation). |
| 6.3 | ▶︎ auto | ci | Subsequent releases are tag-driven and need no manual setup — just bump versions, commit, tag, push. |

## Phase 7 · Optional / future

These are nice-to-haves, not blockers.

| # | Status | Owner | Item |
|---|--------|-------|------|
| 7.1 | ⏸ optional | user | Publish to Docker Hub in addition to GHCR. See [`docs/release.md`](release.md) and extend the `publish-ghcr` job to log into Docker Hub too. Needs `DOCKERHUB_USERNAME` + `DOCKERHUB_TOKEN` secrets. |
| 7.2 | ⏸ optional | user | Code coverage upload (codecov.io or coveralls). Add `pytest --cov` to CI and a coverage-upload step. |
| 7.3 | ⏸ optional | user | Set up sigstore/Cosign signing for the container images. The `gh attestation` flow already covers GHCR; explicit signing helps Docker Hub consumers. |
| 7.4 | ⏸ optional | user | Add `docs/tools/<name>.md` for each new tool added to `shimkit/tools/`. See [`CONTRIBUTING.md`](../CONTRIBUTING.md#adding-a-new-tool). |
| 7.5 | ⏸ optional | user | Move docs to a published site (mkdocs-material or GitHub Pages) if SEO / discoverability matters more than raw GitHub rendering. |
| 7.6 | ⏸ optional | user | Add a `CITATION.cff` if the tool gets cited academically. |

---

## Critical path summary

For the **minimum** to ship `shimkit 0.1.0` to end users:

```
2.5  Make repo public
  └─► 3.2  Create TAP_GITHUB_TOKEN
        └─► 4.1  PyPI account + 2FA
              └─► 4.2  Configure trusted publisher
                    └─► 5.3  git tag v0.1.0 && git push origin v0.1.0
                          └─► 5.5  Verify
```

`3.2` can be done in parallel with `4.1` + `4.2` — they have no
cross-dependencies. `2.5` (visibility) blocks the install one-liner
URL but does **not** block PyPI / GHCR / Homebrew tap publishes; those
all work on private repos too.

Strictly, if you only care about publishing to PyPI (not the curl
one-liner), `2.5` is also optional — but the published `README.md`
will then show a broken install command, so do it.

---

## Status cheat sheet

| Status | Meaning |
|--------|---------|
| ✅ done | Already in place. No action needed. |
| ⏳ pending | Needs your action — see the linked command/UI path. |
| ▶︎ auto | Triggered automatically by the release workflow / Dependabot. |
| ⏸ optional | Nice-to-have, not required to ship. |
| ⚠ blocker | Downstream items can't proceed until this is done. |
