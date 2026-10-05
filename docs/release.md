# Release process

Releases are tag-driven: push a `vX.Y.Z` tag and GitHub Actions builds, attests and publishes it.

> **Current channels (as of v0.11.0):** GitHub Release wheel + sdist
> + SBOM, AND PyPI (when the trusted-publisher config below is in
> place). PyPI publishing was deferred between v0.5.0 and v0.10.0
> and restored in v0.11.0; the first PyPI upload happens on the
> next tag after the trusted-publisher prerequisites are in place.
>
> The Homebrew tap path and the GHCR container were removed
> earlier. The tap is recorded under
> [Homebrew tap (abandoned)](#homebrew-tap-abandoned) if anyone
> wants to re-add it; the GHCR container was removed in v0.2.2
> because it was always a testing artifact, not a documented
> install method.

For the one-time PyPI / npm / Docker setup (trusted publishers,
environments, tokens), this repo follows the standard
[PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
flow. The recipe is below. The generic, org-wide release gate (writing
review, security, CI hardening, supply chain, first-release steps) is
the Simtabi shipping checklist, which is kept outside this repository;
this page carries only what is specific to shimkit.

## Release readiness

What stands between "code is ready" and "users can `pip install
shimkit`", in dependency order. Each state below says when it was last
checked.

| # | Item | State |
|---|------|-------|
| 1 | GitHub Release channel (wheel + sdist + SBOM) | Live. Every release from v0.5.0 onward is on the GitHub Release page. |
| 2 | Ruleset on `main` requiring a pull request and passing checks | Active (checked 2026-10-05 with `gh api repos/simtabi/shimkit/rulesets`): ruleset "default branch: pull request and passing checks", requiring every `test` matrix cell, `security`, `build`, both `smoke` cells and both `adguard` integration jobs. |
| 3 | `pypi` GitHub Environment | Exists (checked 2026-10-05 with `gh api repos/simtabi/shimkit/environments`). The OIDC token every `publish-pypi` run presents already carries `sub: repo:simtabi/shimkit:environment:pypi`. Optionally add a Required Reviewer rule for a human gate before upload. |
| 4 | PyPI account with 2FA | Pending, owner action: <https://pypi.org/account/register/>. |
| 5 | PyPI trusted publisher for `shimkit` | **Pending, owner action, and the one blocker left.** See [PyPI trusted-publisher setup](#pypi-trusted-publisher-setup). |
| 6 | TestPyPI rehearsal | Optional. Configure a `testpypi` trusted publisher at <https://test.pypi.org/manage/account/publishing/> and a `testpypi` GitHub environment to rehearse a release on TestPyPI before real PyPI. |
| 7 | First PyPI upload | Automatic: the next tagged release after item 5 publishes to PyPI. Then verify with `pip install shimkit` (no `--index-url`), which should resolve to the latest PyPI version. |

Critical path for the next release to reach PyPI:

```
3  Create the pypi GitHub Environment   (done)
  └─► 4  PyPI account + 2FA
        └─► 5  Configure trusted publisher
              └─► next tag → auto-publishes
```

If only the GitHub Release wheel is acceptable, **none of these are
required**: that channel works today and has shipped every release
since v0.5.0.

### Why PyPI has never received an upload

Every `publish-pypi` run from v0.11.0 through v0.19.0 (nine releases)
failed the token exchange with
`invalid-publisher: valid token, but no corresponding publisher`, and `https://pypi.org/pypi/shimkit/json`
answers 404 (checked 2026-10-05). The GitHub side is correct; pypi.org
has no publisher registered.

### Publishing past tags after the publisher exists

Failed uploads on past tags can **not** be fixed with "Re-run failed
jobs": `publish-pypi` downloads the `dist` artifact from its run's
`build` job, and those artifacts expire after 90 days (v0.11.0 to
v0.19.0 ran 2026-05-15/16). Dispatch the whole workflow on the tag
instead, which rebuilds and uploads:

```bash
gh workflow run release.yml --repo simtabi/shimkit --ref v0.19.0
```

To publish older releases retroactively, dispatch `release.yml` the
same way on each tag (`--ref vX.Y.Z`). `publish-pypi` sets
`skip-existing: true`, so a version already on PyPI is skipped rather
than failing the run.

## Gates a release depends on

CI (`ci.yml`) runs on macOS + Ubuntu × Python 3.10/3.11/3.12/3.13 with
the jobs `test`, `security`, `build`, `smoke`, `adguard-integration`
and `adguard-mutating-integration`. The `test` job carries ruff
(strict), mypy (strict, pydantic plugin), shellcheck, bandit (`-ll`,
fail on medium and above) and pip-audit (`--skip-editable`); at v0.12.0
the suite was 1027 pytest cases at 85% coverage. Coverage uploads to
codecov.io (wired in v0.12.0, with the coverage badge in the README).
Dependabot opens weekly PRs for pip and GitHub Actions updates.

Repository setup that the release path assumes is in place: the
`src/` layout with the hatchling backend, `py.typed` and the bundled
`defaults.json` (the wheel builds cleanly with `python -m build`); the
org-style docs (`README.md`,
`docs/{installation,configuration,architecture,release,tools/*}.md`
with a `docs/tools/<name>.md` page for every shipped tool,
`CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`,
`CODE_OF_CONDUCT.md`); issue and PR templates, Dependabot and
pre-commit; and the public `simtabi/shimkit` repository with `main` as
default branch, description, homepage, topics, Issues and Discussions.
Commits use the noreply identity `imanimanyara@users.noreply.github.com`;
the ID-prefixed form `19682005+imanimanyara@users.noreply.github.com`
recorded in the old checklist is no longer what the checkout is
configured with.

What each gate validates, and what is deliberately left out, is in
[`validation-scope.md`](validation-scope.md).

## Cutting a release

```bash
# 1. Bump the version in BOTH files (must match, the `guard` job enforces):
#    pyproject.toml::project.version
#    src/shimkit/__init__.py::__version__

# 2. Update CHANGELOG.md with the new entry (move [Unreleased] to [X.Y.Z]).

# 3. Commit on a branch and open a pull request; main only changes through a PR
#    (its ruleset requires one, with passing checks):
git switch -c release/vX.Y.Z
git commit -am "release: vX.Y.Z"
git push -u origin release/vX.Y.Z
gh pr create --title "Release vX.Y.Z" --body "..."

# 4. After the PR merges, tag the merge commit and push only the tag:
git switch main && git pull --ff-only
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
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
             │                     wheel + sdist + SBOM attached.
             │
             ▼
         verify-attestation ────── download the released wheel + sdist
                                   and run `gh attestation verify`
                                   on each (wired in v0.12.0).
```

`publish-pypi` and `github-release` run in parallel after `build`
— a PyPI outage doesn't block the GitHub Release upload, and vice
versa. `verify-attestation` reads the provenance back from Sigstore's
transparency log after the release exists, so a misconfigured publish
flow fails visibly instead of shipping unattested artifacts.

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
   | Workflow name | `release.yml` |
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
succeeds, so you can fix the PyPI side at your leisure and then
dispatch the workflow against the same tag (`workflow_dispatch`, see
[Publishing past tags](#publishing-past-tags-after-the-publisher-exists));
"Re-run failed jobs" only works while the run's `dist` artifact has
not expired.

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
# Bump versions and the CHANGELOG on a release branch, merge it through a PR,
# then tag the merge commit and push only the tag:
git switch main && git pull --ff-only && git tag -a vX.Y.Z -m "Release vX.Y.Z" && git push origin vX.Y.Z
```

CI does everything else. If the `pypi` environment has Required
Reviewers configured, you'll get a GitHub notification asking you to
approve before publish.

## Homebrew tap (abandoned)

Distribution through a Homebrew tap was scoped in the original release
plan but never restored after PyPI was deferred, and `release.yml`
has no tap job today. The live channels are PyPI and the GitHub
Release page.

If a tap is wanted in future:

1. Create `simtabi/homebrew-tap` (public repo, empty `Formula/` dir):
   `gh repo create simtabi/homebrew-tap --public`.
2. Create a `TAP_GITHUB_TOKEN` secret: a fine-grained PAT scoped to
   that repo with Contents read/write (Settings → Secrets → Actions).
3. Add a `bump-homebrew-tap` job to `release.yml` after
   `github-release`, marked `continue-on-error` so a tap failure
   never fails the release; the formula is simply not bumped on that
   release.

## Optional and future

- Move the docs to mkdocs-material on GitHub Pages if SEO and
  discoverability come to matter more than plain GitHub rendering.
- Add a `CITATION.cff` if the tool gets cited academically.

---

[← Docs index](../README.md#documentation)
