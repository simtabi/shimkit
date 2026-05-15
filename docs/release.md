# Release process

Releases are **tag-driven**. Push a `vX.Y.Z` tag, GitHub Actions does
the rest.

> **Current channels (as of v0.11.0):** GitHub Release wheel + sdist
> + SBOM, AND PyPI (when the trusted-publisher config below is in
> place). PyPI publishing was deferred between v0.5.0 and v0.10.0
> and restored in v0.11.0; the first PyPI upload happens on the
> next tag after the trusted-publisher prerequisites are in place.
>
> The Homebrew tap path and the GHCR container were removed
> earlier — Homebrew tap is in `shipping-checklist.md` Phase 5
> if anyone wants to re-add it; the GHCR container was always
> meant as a testing artifact, not a distribution channel.

For the one-time PyPI / npm / Docker setup (trusted publishers,
environments, tokens), this repo follows the standard
[PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
flow. The recipe is below; ask the team if you need the org-wide
reference for cross-project conventions.

## Ship checklist

Do these in dependency order:

| # | Step | Where |
|---|------|-------|
| 1 | Claim `shimkit` on PyPI + configure trusted publisher | <https://pypi.org/manage/account/publishing/> |
| 2 | Create `pypi` GitHub Environment | `simtabi/shimkit` Settings → Environments |
| 3 | Create `simtabi/homebrew-tap` (public repo, empty `Formula/` dir) | `gh repo create simtabi/homebrew-tap --public` |
| 4 | Create `TAP_GITHUB_TOKEN` secret (fine-grained PAT, Contents R/W on tap repo) | Settings → Secrets → Actions |
| 5 | Cut `v0.1.0` (or whatever's next) | `git tag vX.Y.Z && git push origin vX.Y.Z` |

Step 3's `bump-homebrew-tap` workflow step `continue-on-error`s, so
step 5 will succeed even if step 3 isn't done yet — the formula just
won't be auto-bumped on that release.

## Cutting a release

```bash
# 1. Bump the version in BOTH files (must match, the `guard` job enforces):
#    pyproject.toml::project.version
#    src/shimkit/__init__.py::__version__

# 2. Update CHANGELOG.md with the new entry (move [Unreleased] to [X.Y.Z]).

# 3. Commit and tag:
git commit -am "release: vX.Y.Z"
git tag vX.Y.Z
git push origin main vX.Y.Z
```

## What `release.yml` does

```
push tag v*
    │
    ▼
┌── guard ──────────────────────────────────────────────────────┐
│  tag matches pyproject.toml::project.version?                 │
│  CHANGELOG has [X.Y.Z] or [Unreleased] section?               │
│  fail with annotation otherwise                               │
└───────────────────────────────────────────────────────────────┘
    │
    ▼
┌── build ─────────────────────────────────────────────────────┐
│  python -m build  (sdist + wheel)                            │
│  anchore/sbom-action  →  dist/shimkit-sbom.spdx.json         │
│  actions/attest-build-provenance over the wheel + sdist      │
│  upload artifact: dist/                                      │
└───────────────────────────────────────────────────────────────┘
    │       │
    │       └──► publish-pypi ──── trusted-publishing (OIDC)
    │                              upload wheel + sdist to PyPI
    │                              (skip-existing: true for reruns)
    │
    └──► github-release ────────── create the GH Release with
                                   wheel + sdist + SBOM attached.
```

`publish-pypi` and `github-release` run in parallel after `build`
— a PyPI outage doesn't block the GitHub Release upload, and vice
versa.

### PyPI trusted-publisher setup

Required once per project, by a maintainer with PyPI write access:

1. **PyPI side** — log in, then visit
   <https://pypi.org/manage/account/publishing/> and add a pending
   publisher with:

   | Field | Value |
   |-------|-------|
   | PyPI Project Name | `shimkit` |
   | Owner | `simtabi` |
   | Repository name | `shimkit` |
   | Workflow filename | `release.yml` |
   | Environment name | `pypi` |

2. **GitHub side** — Settings → Environments → New environment
   named `pypi`. No secrets required; OIDC provides credentials
   at runtime. Optionally add a Required Reviewer rule if you
   want a human gate before the upload.

3. **First release after setup** — tag and push as normal. The
   `publish-pypi` job will pick up the trusted-publisher config
   automatically.

If either side is missing, the workflow fails at the `publish-pypi`
step with `invalid-publisher`. The `github-release` job still
succeeds, so you can fix the PyPI side at your leisure and re-run
the workflow against the same tag via `workflow_dispatch`.

## Verifying a release

```bash
release=v0.2.2

# Wheel from the GitHub Release page
pip install --user "https://github.com/simtabi/shimkit/releases/download/${release}/shimkit-${release#v}-py3-none-any.whl"
shimkit version

# GitHub Release SBOM
curl -fsSL "https://github.com/simtabi/shimkit/releases/download/${release}/shimkit-sbom.spdx.json" -o /tmp/sbom.json
jq .name /tmp/sbom.json   # should print "shimkit"
```

## Cancelling / yanking

| Situation | Action |
|-----------|--------|
| Caught a bad release before consumers pulled | Cancel the running workflow + delete the tag (`git push --delete origin vX.Y.Z`); PyPI immutable so a re-tag with the same version won't republish — bump and re-release |
| Bad release already on PyPI | [Yank](https://pypi.org/help/#yanked) it (hides from `pip install` defaults but preserves the file). Release a patch fix |
| Bad container image | `gh release delete` removes the GH Release; for GHCR, repo → Packages → version → Delete. Container deletion is permanent — re-publish with a new patch tag |

## Subsequent releases

Once the first release has gone through, every subsequent one is just:

```bash
# Bump versions, commit, tag, push:
git commit -am "release: vX.Y.Z" && git tag vX.Y.Z && git push origin main vX.Y.Z
```

CI does everything else. If the `pypi` environment has Required
Reviewers configured, you'll get a GitHub notification asking you to
approve before publish.
