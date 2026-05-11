# Releasing shimkit

All the things that need to exist outside this repo before the first
release, plus the recipe for cutting a release once they do.

## Ship checklist

Do these in order. Each step is independent — pausing between them is
fine.

| # | Step | Where | What it gates |
|---|------|-------|---------------|
| **D4** | Rename GitHub repo `java-update-manager` → `shimkit` | GitHub UI or `gh` | Public URLs to match the new name |
| **D1a** | Claim `shimkit` on PyPI | <https://pypi.org/account/register/> if needed | Publishing |
| **D1b** | Configure PyPI trusted publisher (OIDC) | <https://pypi.org/manage/account/publishing/> | Tokenless publish from CI |
| **D3** | Create `pypi` GitHub Environment | Repo Settings → Environments | OIDC scope binding |
| **D2** | Create `simtabi/homebrew-tap` repo | GitHub UI or `gh` | brew install one-liner |
| **D2a** | Add `TAP_GITHUB_TOKEN` secret | Repo Settings → Secrets | Auto-bump after release |
| **D5** | Cut `v0.1.0` | `git tag` + push | Everything goes live |

The release workflow's `bump-homebrew-tap` step `continue-on-error`s, so
D5 can happen before D2 is set up — the formula just won't be bumped
automatically that one time.

---

## D4 — Rename the GitHub repo

The local folder is already `shimkit`. The GitHub repo is still
`simtabi/java-update-manager`. Rename it so:

- `git push` works against the new name
- The `simtabi/shimkit` install one-liner URL resolves
- GitHub auto-creates a redirect from the old name (kept for 12 months
  unless the new name is taken by someone else first)

```bash
# Authenticated as a repo admin:
gh repo rename shimkit -R simtabi/java-update-manager

# Update your local remote:
git remote set-url origin git@github.com:simtabi/shimkit.git
```

Verify with `gh repo view simtabi/shimkit`. Old URLs (issues, PRs, raw
content) will 301 to the new name automatically.

## D1a — Claim `shimkit` on PyPI

If you don't already have a PyPI account, register at
<https://pypi.org/account/register/> with 2FA enabled (PyPI requires it
for publishers).

You don't need to upload anything to claim the name; the trusted publisher
configuration in D1b reserves it on the first OIDC-authenticated publish
attempt. PyPI is first-come-first-served — confirm
`pip install shimkit` 404s (it does as of this writing) and proceed.

## D1b — Configure PyPI trusted publisher

1. Sign in to PyPI.
2. Go to **Your projects** → **Add a pending publisher**
   (<https://pypi.org/manage/account/publishing/>).
3. Fill in:
   - **Project name:** `shimkit`
   - **Owner:** `simtabi`
   - **Repository name:** `shimkit`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
4. Save.

This binds the GitHub repo + workflow + environment to PyPI uploads.
The `pypa/gh-action-pypi-publish` action in `release.yml` will request
an OIDC token at publish time and PyPI will accept it because of this
binding. No API tokens, no secrets, nothing to rotate.

## D3 — Create the `pypi` GitHub Environment

1. Go to **Settings → Environments → New environment**.
2. Name it exactly `pypi` (matches `release.yml`'s
   `environment: pypi` declaration on the `publish-pypi` job).
3. Optional but recommended:
   - **Required reviewers:** add yourself. Every release will prompt for
     a human to approve before publishing — cheap safety net.
   - **Wait timer:** 5 minutes. Lets you cancel an accidental tag push.
4. Save. No secrets to add — OIDC handles auth.

## D2 — Create the Homebrew tap

```bash
# Create the tap repo on GitHub (public, empty).
gh repo create simtabi/homebrew-tap --public --description "Homebrew tap for simtabi tools"

# Clone it and scaffold a Formula/ dir.
git clone git@github.com:simtabi/homebrew-tap.git
cd homebrew-tap
mkdir Formula
printf "# simtabi/homebrew-tap\n\nFormulae:\n- shimkit\n" > README.md
git add . && git commit -m "scaffold tap" && git push
```

The release workflow will write `Formula/shimkit.rb` on the first
successful publish. If you want to seed the formula manually before
that, see `installer/homebrew-formula.rb.template` and:

```bash
brew tap-new simtabi/tap --no-git
brew create --tap simtabi/tap --python \
  https://files.pythonhosted.org/packages/source/s/shimkit/shimkit-0.1.0.tar.gz
brew update-python-resources Formula/shimkit.rb
brew audit --new --strict Formula/shimkit.rb
git add Formula && git commit -m "shimkit 0.1.0" && git push
```

## D2a — Add the tap-bump secret

The `bump-homebrew-tap` job in `release.yml` needs a token to push to
the tap repo.

1. Create a fine-grained PAT at <https://github.com/settings/tokens?type=beta>.
   - **Repository access:** select `simtabi/homebrew-tap`
   - **Permissions → Repository permissions → Contents:** Read and write
   - **Permissions → Repository permissions → Pull requests:** Read and write
   - **Expiration:** 90 days (renew when it expires)
2. Copy the token.
3. In `simtabi/shimkit` → **Settings → Secrets and variables → Actions
   → New repository secret**, name it `TAP_GITHUB_TOKEN`, paste the
   token.

## D5 — Cut the first release

```bash
git checkout main
git pull

# Bump the version (already 0.1.0 at the moment of writing — bump to
# whatever you're cutting):
#   pyproject.toml :: project.version
#   src/shimkit/__init__.py :: __version__
# Keep them identical; the release.yml `guard` job will block mismatches.

git commit -am "release: v0.1.0"
git tag v0.1.0
git push origin main v0.1.0
```

The `release.yml` workflow runs on the tag push:

1. `guard` — verifies the tag matches `pyproject.toml`'s version. Fails
   loud if not.
2. `build` — builds sdist + wheel via `python -m build`. Generates
   `installer/install.sh.sha256`. Uploads artifacts.
3. `publish-pypi` — requests OIDC token, publishes to PyPI. Trusted
   publisher binding from D1b authenticates the call.
4. `github-release` — creates the GitHub Release with `install.sh`,
   `install.sh.sha256`, the wheel, and the sdist attached. Auto-generates
   release notes from commits since the last tag.
5. `bump-homebrew-tap` — updates the formula in `simtabi/homebrew-tap`.
   Soft-fails if the tap doesn't exist yet (D2 not done).

## Verifying the install one-liner

```bash
curl -fsSL --proto '=https' --tlsv1.2 \
  https://github.com/simtabi/shimkit/releases/latest/download/install.sh \
  | sh
shimkit version
```

For paranoid installs:

```bash
release=v0.1.0
base=https://github.com/simtabi/shimkit/releases/download/${release}
curl -fsSL --proto '=https' --tlsv1.2 "${base}/install.sh" -o install.sh
curl -fsSL --proto '=https' --tlsv1.2 "${base}/install.sh.sha256" -o install.sh.sha256
sha256sum -c install.sh.sha256
sh install.sh
```

## Subsequent releases

After D1–D4 are in place, every release is just:

```bash
# bump version in both files, commit, tag, push:
git commit -am "release: vX.Y.Z" && git tag vX.Y.Z && git push origin main vX.Y.Z
```

CI does everything else. If the PyPI environment has Required Reviewers,
you'll get a GitHub notification asking you to approve before publish.
