# Shipping checklist

Everything that needs to happen between "code is ready" and "users can
`pip install shimkit`". Items are listed in **dependency order** —
later items assume earlier ones are done.

> **Status as of v0.12.0** — Eleven releases are live on the GitHub
> Release page (v0.5.0 through v0.12.0). PyPI publishing was
> restored in v0.11.0 but the first PyPI upload is blocked on the
> user-side trusted-publisher setup (Phase 4). The Homebrew tap
> path was originally planned for Phase 3 but never restored — the
> abandoned-channel rationale is in [`docs/release.md`](release.md).

Three columns:

- **Status** — `done` (already in place), `pending` (someone needs
  to act), `optional`, or `abandoned`.
- **Owner** — `code` (already shipped in the repo), `user` (you, via
  web UI or local terminal), or `ci` (the release workflow does it
  automatically when triggered).
- **Item** — what needs doing, with the exact command or click path.

For what each automated and manual gate validates (and what we
intentionally don't validate), see
[`validation-scope.md`](validation-scope.md).

---

## Phase 1 · Code & repo setup

| # | Status | Owner | Item |
|---|--------|-------|------|
| 1.1 | ✅ done | code | shimkit package built: src/ layout, hatchling backend, py.typed, bundled `defaults.json`. Wheel builds cleanly (`python -m build`). |
| 1.2 | ✅ done | code | Tests pass: 1027 pytest cases at 85% coverage. ruff strict, mypy strict + pydantic plugin, shellcheck, bandit (`-ll`, fail on medium+), pip-audit (`--skip-editable`). |
| 1.3 | ✅ done | code | CI workflow — macOS + Ubuntu × Python 3.10/3.11/3.12/3.13. Jobs: `test`, `security`, `build`, `smoke`, `adguard-integration`, `adguard-mutating-integration`. |
| 1.4 | ✅ done | code | Release workflow — `guard` → `build` (sdist + wheel + SBOM + attestation) → `publish-pypi` (restored v0.11.0) + `github-release` in parallel. |
| 1.5 | ➖ n/a | code | (Reserved.) Earlier the project shipped a container image; that path was removed in v0.2.2 because Docker was a testing artifact, not a documented install method. |
| 1.6 | ✅ done | code | Org-style docs: `README.md`, `docs/{installation,configuration,architecture,release,tools/*}.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`. |
| 1.7 | ✅ done | code | Community hygiene: ISSUE_TEMPLATE/, PULL_REQUEST_TEMPLATE, dependabot, pre-commit. |
| 1.8 | ⏳ pending | user | Configure branch protection on `main`: require `test`, `security`, `build`, `smoke` checks before merge. Repo Settings → Branches → Add rule. |

## Phase 2 · GitHub remote

| # | Status | Owner | Item |
|---|--------|-------|------|
| 2.1 | ✅ done | user | Repo exists at `simtabi/shimkit`. Default branch `main`. Public. |
| 2.2 | ✅ done | user | Repo metadata set: description, homepage, topics. Issues + Discussions enabled. |
| 2.3 | ✅ done | user | Local git identity scoped to noreply (`19682005+imanimanyara@users.noreply.github.com`). |
| 2.4 | ⏳ **pending** | **user** | **Create the `pypi` GitHub Environment.** ⚠ blocker for the v0.11.0+ `publish-pypi` job. Settings → Environments → New environment named `pypi`. No secrets required (OIDC provides credentials). Optionally add a Required Reviewer rule for a human gate before upload. |

## Phase 3 · Homebrew tap — abandoned

Distribution via Homebrew tap was scoped in this checklist's original
shape but never restored after the Phase 4 PyPI deferral. The current
distribution channels are PyPI (Phase 4) and the GitHub Release page.

If a tap is desired in the future:

1. Create `simtabi/homebrew-tap` (public repo, empty `Formula/` dir).
2. Create a `TAP_GITHUB_TOKEN` fine-grained PAT scoped to that repo
   (Contents R/W).
3. Add a `bump-homebrew-tap` job to `release.yml` after
   `github-release`.

## Phase 4 · PyPI — restored in v0.11.0

The `publish-pypi` job exists in `release.yml` and runs in parallel
with `github-release` after `build`. First upload blocked on the
user-side trusted-publisher setup.

| # | Status | Owner | Item |
|---|--------|-------|------|
| 4.1 | ⏳ pending | user | **Register / sign in to PyPI** and enable 2FA. <https://pypi.org/account/register/>. |
| 4.2 | ⏳ **pending** | **user** | **Configure the trusted publisher** for `shimkit`. <https://pypi.org/manage/account/publishing/> → Add a new pending publisher → GitHub. |
|  |  |  | • PyPI Project Name: `shimkit` |
|  |  |  | • Owner: `simtabi` |
|  |  |  | • Repository name: `shimkit` |
|  |  |  | • Workflow name: `release.yml` |
|  |  |  | • Environment name: `pypi` |
| 4.3 | ⏸ optional | user | (Dry-run only) Configure a `testpypi` trusted publisher at <https://test.pypi.org/manage/account/publishing/> + a `testpypi` GitHub environment if you want to rehearse a release on TestPyPI before hitting real PyPI. |

After 2.4 + 4.1 + 4.2 are done, the next tag will publish to PyPI
automatically. Failed PyPI uploads on past tags (v0.11.0, v0.12.0)
can be re-run via Actions → failed run → "Re-run failed jobs".

## Phase 5 · First PyPI upload

Prerequisites: 2.4 + 4.1 + 4.2 all done.

| # | Status | Owner | Item |
|---|--------|-------|------|
| 5.1 | ▶︎ auto | ci | The next tagged release after 4.2 publishes to PyPI automatically. |
| 5.2 | ⏳ pending | user | Verify the upload: `pip install shimkit` (no `--index-url`) should resolve to the latest PyPI version. |
| 5.3 | ⏸ optional | user | Re-run failed `publish-pypi` jobs against tags v0.11.0+ to retroactively publish past releases. |

## Phase 6 · Post-release / ongoing

| # | Status | Owner | Item |
|---|--------|-------|------|
| 6.1 | ▶︎ auto | ci | **Dependabot** opens weekly PRs for pip + GitHub Actions updates. |
| 6.2 | ▶︎ auto | ci | Subsequent releases are tag-driven and need no manual setup — bump versions, commit, tag, push. |

## Phase 7 · Optional / future

| # | Status | Owner | Item |
|---|--------|-------|------|
| 7.1 | ✅ done | code | Code coverage upload to codecov.io. Wired in v0.12.0; coverage badge in README. |
| 7.2 | ✅ done | code | `docs/tools/<name>.md` for every shipped tool. |
| 7.3 | ⏸ optional | user | Move docs to mkdocs-material on GitHub Pages if SEO / discoverability matters more than raw GitHub rendering. |
| 7.4 | ⏸ optional | user | Add a `CITATION.cff` if the tool gets cited academically. |
| 7.5 | ✅ done | code | `gh attestation verify` smoke test post-release. Wired in v0.12.0. |

---

## Critical path summary

For the next release to publish to PyPI:

```
2.4  Create the pypi GitHub Environment
  └─► 4.1  PyPI account + 2FA
        └─► 4.2  Configure trusted publisher
              └─► next tag → auto-publishes
```

If only the GitHub Release wheel is acceptable, **none of these are
required** — that channel works today and has shipped 11+ releases.

---

## Status cheat sheet

| Status | Meaning |
|--------|---------|
| ✅ done | Already in place. No action needed. |
| ⏳ pending | Needs your action — see the linked command/UI path. |
| ▶︎ auto | Triggered automatically by the release workflow / Dependabot. |
| ⏸ optional | Nice-to-have, not required to ship. |
| 🗑 abandoned | Originally scoped, intentionally not pursued. |
| ⚠ blocker | Downstream items can't proceed until this is done. |
