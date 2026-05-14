# Release process

Releases are **tag-driven**. Push a `vX.Y.Z` tag, GitHub Actions does
the rest.

> **Current channels (as of v0.2.2):** GHCR container + GitHub
> Release wheel. PyPI publishing is **deferred** — the
> `publish-pypi` and `bump-homebrew-tap` jobs are removed from
> `release.yml`. The "Phase 4 · PyPI" section of
> [`shipping-checklist.md`](shipping-checklist.md) documents how to
> re-enable them.

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
    │
    └──► github-release ─── creates the GH Release with wheel +
                            sdist + SBOM attached.
```

As of v0.2.2 the release pipeline ships **only** the GitHub Release
artifact set. The `publish-pypi`, `publish-ghcr`, and
`bump-homebrew-tap` jobs that previously fanned out from `build`
were removed: PyPI publishing is deferred ([Phase 4 of
shipping-checklist.md](shipping-checklist.md)), and the GHCR /
Dockerfile path was always meant as a testing artifact rather than
a distribution channel (see `prompt.md`'s install-method list).

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
