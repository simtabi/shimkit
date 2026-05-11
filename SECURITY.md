# Security policy

## Reporting a vulnerability

**Do not file public issues for security reports.** Email security
findings to `security@simtabi.com` (preferred) or use GitHub's
private vulnerability reporting:

<https://github.com/simtabi/shimkit/security/advisories/new>

We aim to acknowledge reports within 72 hours. Please include:

- A description of the issue and its impact
- Steps to reproduce, including affected version(s)
- Proof-of-concept code, if applicable
- Whether you'd like public credit for the report

We will keep you informed as we investigate and patch.

## Supported versions

Security fixes go to the latest minor release. Older minors receive
fixes only for severities at or above High.

| Version       | Status                  |
|---------------|-------------------------|
| 0.1.x         | Current — supported     |

## Scope

The shimkit codebase, the bundled `installer/install.sh`, the
container image at `ghcr.io/simtabi/shimkit`, and the GitHub Actions
workflows in this repository are in scope.

Out of scope:

- The upstream tools shimkit invokes (Homebrew, apt, dnf, etc.).
  Report those to their respective maintainers.
- The Java versions shimkit installs. Java security issues belong with
  Eclipse Adoptium / Oracle / your distro's openjdk maintainers.
- Third-party Python packages shimkit depends on. Report those to the
  package maintainers; we'll bump shimkit's dep ranges once their fix
  is published.

## Disclosure

We coordinate disclosure with reporters. Default policy is to publish
an advisory once a fix is released, crediting the reporter (with
their permission) and providing CVE assignment when warranted.

## Trusted publishing

shimkit is published to PyPI via OIDC trusted publishers — no API
tokens. The container image is signed with the GitHub Actions OIDC
provenance attestation. Verifying:

```bash
pip install shimkit
pip show shimkit                                  # confirm origin

# Container provenance:
gh attestation verify oci://ghcr.io/simtabi/shimkit:latest \
  --repo simtabi/shimkit
```
