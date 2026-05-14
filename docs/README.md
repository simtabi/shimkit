# shimkit documentation

The repo root has the short version. This directory has the long
version.

## Getting started

- **[Installation](installation.md)** — uv, pipx, pip, Homebrew, the
  curl one-liner, and how `shimkit self-update` works.
- **[Configuration](configuration.md)** — the JSON config layer, where
  files live, override precedence, the schema.

## Tools

shimkit is a collection. Each tool gets its own page:

- **[`shimkit java`](tools/java.md)** — OpenJDK version manager.
  Install / list / switch / upgrade / uninstall / remove-oracle.
- **[`shimkit shell`](tools/shell.md)** — Cross-PM shell upgrader for
  bash / zsh / fish / ksh.
- **[`shimkit dns`](tools/dns.md)** — macOS DNS resolver recovery.
  Diagnose, flush, fix (6-step escalation), test, rollback.
- **[`shimkit adguard`](tools/adguard.md)** — AdGuard Home port-conflict
  fixer (Linux). API-first, ruamel.yaml fallback.
- **[`shimkit docker-clean`](tools/docker-clean.md)** — Docker resource
  cleanup (Linux + macOS + WSL). docker-py SDK + buildx-aware prune.

Top-level utilities (not tools):

- `shimkit config` — inspect, edit, validate user configuration.
  Documented in [Configuration](configuration.md).
- `shimkit doctor` — system diagnostics for bug reports. No dedicated
  page; run it and the output is self-documenting.
- `shimkit self-update` — keep shimkit current. Documented in
  [Installation](installation.md#updates).

## Development

- **[Architecture](architecture.md)** — how the core/tools split
  works, the load-bearing rules, how to add a new tool.
- **[Onboarding](onboarding.md)** — practical walkthrough for getting
  productive: setup, the 5 rules with grep recipes, the canonical
  recipe for adding a new tool, common dev tasks, debugging guide.
- **[Release process](release.md)** — cutting a new version, the CI
  pipeline, what each release job does.
- **[Shipping checklist](shipping-checklist.md)** — every step from
  "code ready" to "users can install", in dependency order. Tracks
  what's done vs what still needs your action.
- **[Validation scope](validation-scope.md)** — what's in scope for
  automated + manual gates, what's deliberately out of scope, and
  how to expand the envelope.
- **[Known issues + pending items](plans/known-issues.md)** — checks
  that exist in our scope but can't be automated (and why), coverage
  deferrals, and aspirational follow-ups without owners.

## Release notes

Per-version, user-facing summaries:

- **[`v0.2.0`](release-notes/v0.2.0.md)** — three new tools (`dns`,
  `adguard`, `docker-clean`); uniform CLI surface across all new
  subcommands; argv-list PM templates; container hardening + SBOM
  + attestation.

External references:

- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — coding conventions, test
  patterns, PR expectations.
- [`SECURITY.md`](../SECURITY.md) — vulnerability disclosure.
- [`CHANGELOG.md`](../CHANGELOG.md) — release history.

For shimkit-specific release operations, see
[`release.md`](release.md). For the wider org-level reference on
publishing to PyPI / npm / Docker registries, ask the team — that
guide lives outside this repo.
