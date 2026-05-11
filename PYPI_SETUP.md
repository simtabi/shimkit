# Publishing shimkit to PyPI

A standalone walkthrough for registering and configuring `shimkit` on
[PyPI](https://pypi.org). After this is done once, every `git tag vX.Y.Z`
publishes to PyPI automatically via OIDC — no API tokens to manage.

This document covers PyPI only. For the full ship checklist
(GitHub repo rename, Homebrew tap, etc.), see
[`installer/RELEASE.md`](installer/RELEASE.md).

## Why trusted publishing (OIDC) rather than API tokens

PyPI supports [Trusted Publishers](https://docs.pypi.org/trusted-publishers/),
which binds a GitHub repository + workflow + environment to PyPI uploads.
At release time, the GitHub Action requests an OIDC token from GitHub,
hands it to PyPI, and PyPI authenticates the upload based on the binding
you configured. No long-lived tokens to leak, rotate, or store as
secrets.

Token-based publishing still works but is no longer recommended. This
guide does not cover it.

---

## Step 1 — Create a PyPI account

1. Go to <https://pypi.org/account/register/>.
2. Register an account. Use an organisation email if possible
   (`releases@simtabi.com`, `it@simtabi.com`, etc.). Personal accounts
   work but couple ownership to a single individual.
3. **Verify your email** by clicking the link PyPI sends.
4. **Enable 2FA** (required for publishers as of 2024):
   - PyPI → Account settings → Two factor authentication
   - Either a TOTP app (1Password, Authy, Google Authenticator) or a
     WebAuthn key.

Existing account? Sign in, confirm 2FA is enabled, skip to Step 2.

> The `shimkit` name is currently unclaimed on PyPI
> (`pip install shimkit` 404s). Step 2 reserves it.

---

## Step 2 — Configure the trusted publisher

PyPI supports two flavours:

- **Pending publisher** — used the *very first time* a project name is
  published. PyPI reserves the name on the first OIDC publish.
- **Existing project publisher** — used after the project exists on PyPI.

For shimkit's first release, we use the pending publisher.

1. Sign in to PyPI.
2. Go to <https://pypi.org/manage/account/publishing/>.
3. Scroll to **Add a new pending publisher** → **GitHub**.
4. Fill in **exactly**:

   | Field | Value |
   |-------|-------|
   | PyPI Project Name | `shimkit` |
   | Owner | `simtabi` |
   | Repository name | `shimkit` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

5. Click **Add**.

The values in the table must match the repo's `release.yml` exactly. If
you rename the workflow file, the environment, or transfer the repo,
update the publisher here too.

---

## Step 3 — Create the `pypi` GitHub Environment

The `environment: pypi` declaration on the `publish-pypi` job in
`release.yml` binds OIDC scope to a specific environment in the GitHub
repo. The environment must exist.

1. In `simtabi/shimkit` → **Settings** → **Environments**.
2. **New environment** → name it exactly **`pypi`** (case-sensitive,
   must match `release.yml` and the PyPI publisher config).
3. Configure protection rules (recommended, optional):
   - **Required reviewers**: yourself. Every publish will block on a
     manual approval — a cheap "did I really mean to do that" gate.
   - **Wait timer**: 5 minutes. Allows cancelling an accidental tag
     push.
   - **Deployment branches**: restrict to `main` if your release flow
     only ever cuts from main.
4. Save. **Do not add any secrets** — OIDC handles auth; there's
   nothing to store here.

---

## Step 4 — Cut a release and watch it publish

```bash
# Ensure pyproject.toml::project.version and
# src/shimkit/__init__.py::__version__ are both set to the version
# you're cutting. They must match — the release.yml `guard` job
# will fail loud otherwise.

git tag v0.1.0
git push origin main v0.1.0
```

Watch the Actions tab at <https://github.com/simtabi/shimkit/actions>.
The `release.yml` run will:

1. **guard** — verifies `tag` matches `pyproject.toml::project.version`.
2. **build** — produces `shimkit-X.Y.Z.tar.gz` + `shimkit-X.Y.Z-py3-none-any.whl`.
3. **publish-pypi** — waits for environment approval (if you enabled
   it), requests OIDC token, uploads to PyPI.
4. **github-release** — creates the GitHub Release with installer +
   wheel + sdist + sha256 attached.
5. **bump-homebrew-tap** — pushes the formula bump (soft-fails if the
   tap repo doesn't exist yet).

Within 30 seconds of `publish-pypi` succeeding, the package is live at:

- <https://pypi.org/project/shimkit/>
- `pip install shimkit` — works
- `uv tool install shimkit` — works

---

## TestPyPI dry-run (optional but recommended for big releases)

[TestPyPI](https://test.pypi.org) is a parallel staging instance. Add a
second trusted publisher pointing at it to dry-run a release without
polluting real PyPI.

1. Register at <https://test.pypi.org/account/register/> (separate
   account from production PyPI). Enable 2FA.
2. Go to <https://test.pypi.org/manage/account/publishing/> and add a
   pending publisher with the **same fields as Step 2** but environment
   name `testpypi` (not `pypi`).
3. Create a `testpypi` GitHub environment in the repo.
4. Add a second workflow `release-test.yml` (or a flag in `release.yml`)
   that targets TestPyPI. The action call becomes:

   ```yaml
   - uses: pypa/gh-action-pypi-publish@release/v1
     with:
       repository-url: https://test.pypi.org/legacy/
   ```

5. Push a pre-release tag (e.g. `v0.1.0-rc.1`) to trigger the dry-run.

This is optional. The real release workflow is robust enough that
testing it before the first publish is paranoia, not necessity.

---

## Troubleshooting

### "trusted publisher not found"

You're seeing one of:

- `pypi.org/manage/account/publishing/` shows no pending publisher
  matching your repo
- The publish action fails with `403 Forbidden`

Check, in order:

1. PyPI publisher's **Owner** is `simtabi` (not your username).
2. PyPI publisher's **Repository** is `shimkit` (not
   `java-update-manager` — the old name shouldn't be configured even
   if GitHub still redirects).
3. PyPI publisher's **Workflow** is exactly `release.yml` (the
   filename, not the workflow's `name:` value).
4. PyPI publisher's **Environment** is exactly `pypi` (case-sensitive).
5. The GitHub Environment `pypi` exists in the repo.
6. The workflow's `publish-pypi` job has `environment: pypi`.

### "id-token: write permission denied"

The workflow's job needs:

```yaml
permissions:
  id-token: write
```

at the job or workflow level. `release.yml` declares this at the
workflow level so all jobs inherit it.

### "twine: HTTPError 400 — File already exists"

You're trying to re-upload an already-published version. PyPI is
immutable per (project, version). Bump the version and re-tag.

If you genuinely need to take a version back: PyPI supports
[yanking](https://pypi.org/help/#yanked) (hides from `pip install`
defaults but preserves the file). Project owners can yank from the
release page on PyPI.

### "The 'shimkit' name is taken"

Someone else registered it between when you read this and when you
ran the publish. The pending publisher fails because the name now
belongs to that account.

Options:

- Contact PyPI support (`admin@pypi.org`) — they will transfer
  inactive abandoned projects to active maintainers in some cases.
- Pick a new name: `simtabi-shimkit`, `shimkit-cli`, `shimkitx`.
  Update `pyproject.toml::project.name`, regenerate the wheel, and
  re-register the publisher with the new project name.

---

## Maintenance

- **Rotate the GitHub Environment** if you ever leak its protection
  rules / settings. Delete the environment, recreate, re-add the PyPI
  publisher pointing at the new environment if its name changes.
- **Transfer ownership** when team members leave: PyPI → project page
  → Collaborators → add owners by username.
- **Trusted publisher only** — if you ever generate an API token for
  manual upload, revoke it as soon as you've used it. Long-lived
  tokens defeat the point.

---

## References

- PyPI Trusted Publishers docs:
  <https://docs.pypi.org/trusted-publishers/>
- pypa/gh-action-pypi-publish:
  <https://github.com/pypa/gh-action-pypi-publish>
- TestPyPI: <https://test.pypi.org/>
- Build backend (hatchling) docs:
  <https://hatch.pypa.io/latest/config/build/>
