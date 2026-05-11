# Publishing to npm

**shimkit itself is a Python package and is not published to npm.**

This document exists because npm is the default registry for any
JavaScript/TypeScript tool the team ships in the future. It captures
the conventions we'll use for npm publishes so they don't have to be
re-derived per project.

For shimkit-the-Python-package, see [`PYPI_SETUP.md`](PYPI_SETUP.md).

---

## Why npm trusted publishing (provenance) rather than tokens

As of late 2023, npm supports
[trusted publishers via OIDC](https://docs.npmjs.com/generating-provenance-statements)
(the same model as PyPI's). Binds a GitHub repo + workflow to an npm
package; the publish action requests an OIDC token at release time and
npm verifies the binding. No long-lived tokens to leak.

The publish also embeds a **provenance statement** — a signed attestation
that links the published artifact to the exact git commit + workflow
run. Consumers can verify provenance with `npm audit signatures`.

Token-based publishing still works (and is sometimes necessary for
private registries or org policies that haven't moved to OIDC yet).
This guide covers both.

## Naming a new package

Prefer scoped names under `@simtabi/<package>`:

- Scoped names sidestep the global namespace squatter problem.
- They require `"publishConfig": { "access": "public" }` in
  `package.json` for free OSS publishing.
- They surface ownership in every install command:
  `npm install @simtabi/<package>`.

---

## Step 1 — Create an npm account

1. Register at <https://www.npmjs.com/signup>.
2. Enable 2FA: **Account → 2FA** → choose auth-only (TOTP) for
   account login and publish-auth for OTP-on-publish.
3. Create the `simtabi` org if you don't already have one:
   <https://www.npmjs.com/org/create>.

Existing org member? Skip to Step 2.

## Step 2a — Configure the trusted publisher (OIDC)

1. Sign in to <https://www.npmjs.com>.
2. Navigate to the package's page (after the first publish; for a
   brand-new package, this step happens after Step 4's first publish
   creates the page).
3. **Settings** tab → **Publishing access** → **Configure**.
4. **Add new trusted publisher** → **GitHub Actions**.
5. Fill in:

   | Field | Value |
   |-------|-------|
   | Owner | `simtabi` |
   | Repository | `<your-repo-name>` |
   | Workflow file path | `.github/workflows/release.yml` |
   | Environment | `npm` (optional but recommended) |

6. Save.

Repeat per package — npm trusted publishers are configured
per-package, not per-org (unlike PyPI's pending-publisher flow which
reserves a name).

## Step 2b — Fallback: token-based publishing

If OIDC isn't viable (private registry, org policy, npm Enterprise,
etc.):

1. **Account → Access tokens** → **Generate New Token** → choose
   **Automation** (CI-friendly, bypasses 2FA prompt).
2. Restrict to specific packages if possible.
3. Add as `NPM_TOKEN` secret in the repo's GitHub Actions secrets.

## Step 3 — CI workflow

For a Node.js project, the workflow looks like:

```yaml
name: Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write
  id-token: write      # required for npm provenance

jobs:
  publish-npm:
    runs-on: ubuntu-latest
    environment: npm   # matches trusted publisher config; optional for token auth
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          registry-url: 'https://registry.npmjs.org'

      - name: Install + test
        run: |
          npm ci
          npm test
          npm run build  # if applicable

      - name: Publish to npm
        run: npm publish --provenance --access public
        # If using token auth instead of OIDC, set:
        #   env:
        #     NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
        # The setup-node action wires NODE_AUTH_TOKEN into ~/.npmrc.
```

Key flags:

- `--provenance` — emits the SLSA provenance statement. Requires
  `id-token: write` permission and a CI environment.
- `--access public` — required for scoped packages
  (`@simtabi/whatever`) on the free tier.

## Step 4 — Cut a release

```bash
# Bump version in package.json (npm has an alias for this):
npm version patch    # or minor / major / 0.1.0
git push origin main --follow-tags
```

`npm version` writes the new version to `package.json`, creates a
commit, and tags it (e.g. `v0.1.0`). `--follow-tags` pushes the tag
which triggers `release.yml`.

## Step 5 — Verify

```bash
npm view @simtabi/<package>            # confirm the version is live
npm install -g @simtabi/<package>       # install from npm
npm audit signatures                    # verify provenance attestation
```

`npm audit signatures` fails loudly if the published artifact's
signature can't be verified against the recorded provenance.

---

## TestPyPI-equivalent on npm: a `next` tag

npm doesn't have a parallel staging registry like PyPI's TestPyPI. The
idiom is to publish under a dist-tag:

```bash
npm publish --tag next --provenance --access public
```

Then users opt in with `npm install @simtabi/<package>@next`. The
`latest` tag (default install target) is unaffected. Promote a `next`
release to `latest` with:

```bash
npm dist-tag add @simtabi/<package>@0.2.0-rc.1 latest
```

## Troubleshooting

### `403 You do not have permission to publish "...". Are you logged in as the correct user?`

OIDC binding mismatch — check the trusted publisher's workflow path,
repo, and environment exactly match what's in the workflow.

### `403 Provenance environment misconfigured: missing id-token: write`

The workflow needs `permissions: id-token: write` at the workflow or
job level. Without it, the `--provenance` flag fails before the
publish even attempts.

### `403 Forbidden — scoped package; missing --access public`

Scoped packages default to private. For OSS, add `--access public` to
the publish command (or set `"publishConfig": { "access": "public" }`
in `package.json`).

### `EOTP One-time password required`

You have publish-OTP enabled and are publishing with a Classic token
instead of an Automation token. Either:

- Use an **Automation** token (bypasses OTP for CI).
- Or pre-publish locally with `npm publish --otp=NNNNNN`.

### `ENEEDAUTH` in CI

The `setup-node` action's `registry-url` is missing or wrong. Make
sure it's `https://registry.npmjs.org` exactly. Without the trailing
slash. Without `www.`.

## References

- npm Trusted Publishing:
  <https://docs.npmjs.com/generating-provenance-statements>
- pypa/gh-action-pypi-publish (the PyPI analogue):
  <https://github.com/pypa/gh-action-pypi-publish>
- actions/setup-node: <https://github.com/actions/setup-node>
- npm CLI `publish`: <https://docs.npmjs.com/cli/v10/commands/npm-publish>
