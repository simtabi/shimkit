# Configuration

shimkit reads configuration from a layered chain. Each layer overrides
the one below it:

1. **Bundled defaults** — shipped inside the package at
   `src/shimkit/config/defaults.json`. The source of truth.
2. **User override** — `~/.config/shimkit/shimkit.json` (or
   `$XDG_CONFIG_HOME/shimkit/shimkit.json`).
3. **`$SHIMKIT_CONFIG`** — points at any path; replaces step 2 wholesale.
4. **`NO_COLOR`** env var — forces `ui.color = "never"` regardless.

User overrides are **deep-merged** on top of defaults. Lists are
replaced wholesale (a partial `supported_versions` override does not
append — it replaces).

## CLI

```bash
shimkit config show                       # full resolved config as JSON
shimkit config show ui.color              # one key (dotted path)
shimkit config show tools.java.default_version

shimkit config path                       # show both file paths
shimkit config edit                       # open user file in $EDITOR
                                          # (creates a stub if missing)
shimkit config validate                   # parse defaults+overrides
                                          # against the schema
```

`shimkit config validate` is run automatically on every `shimkit doctor`.

## Where files live

```
src/shimkit/config/defaults.json    # bundled, ships in the wheel
~/.config/shimkit/shimkit.json      # user override (or $XDG_CONFIG_HOME)
```

If `$SHIMKIT_CONFIG=/abs/path/to/file.json` is set, it replaces the
user path entirely. Useful for per-environment overrides without
mutating the user's actual config.

## Schema overview

```jsonc
{
  "schema_version": 1,
  "ui": {
    "color": "auto",                  // auto | always | never
    "back_label": "← Back"            // menu cancel-row label
  },
  "self_update": {
    "enabled": true,
    "check_on_startup": true,
    "github_repo": "simtabi/shimkit"
  },
  "brew": {
    "install_url": "https://raw.githubusercontent.com/Homebrew/install/<sha>/install.sh"
  },
  "tools": {
    "java":         { "default_version": 21, "supported_versions": [...] },
    "shell":        { "supported_shells": ["bash", "zsh", "fish", "ksh"] },
    "dns":          { "test_domains": [...], "dns_servers": {...},
                      "nuclear_confirm_token": "REGENERATE",
                      "reset_confirm_token": "RESET",
                      "backup_dir": "~/Library/Application Support/shimkit/dns-backups" },
    "adguard":      { "install_candidates": [...], "target_ports": [...],
                      "safe_units_to_stop": [...],
                      "resolv_conf_mode": "symlink",
                      "prefer_api_over_yaml": true,
                      "api_base_url": "http://127.0.0.1:80" },
    "docker_clean": { "nuke_confirm_token": "DELETE",
                      "kubernetes_image_patterns": [...],
                      "daemon_verify_timeout_seconds": 30,
                      "default_buildx_prune_all": true }
  },
  "package_managers": {
    "preference_order": ["brew", "apt", "dnf", "yum", "pacman", "apk", "zypper"],
    "definitions":      { /* install/update/upgrade templates per PM */ }
  }
}
```

For the full machine-readable definition, see
[`config/shimkit.schema.json`](../config/shimkit.schema.json) at the
repo root.

## Editor autocomplete

The user file includes a `$schema` key pointing at the published
schema:

```json
{
  "$schema": "https://raw.githubusercontent.com/simtabi/shimkit/main/config/shimkit.schema.json",
  "schema_version": 1,
  ...
}
```

VS Code, JetBrains, neovim with `coc-json` / native LSP, and most
other editors will hint and validate fields as you type.

`shimkit config edit` creates a stub with this header pre-populated.

## What's configurable vs not

**Configurable** (live in `shimkit.json`):

- Supported Java versions, their labels, brew formulae, LTS flags
- Java scan paths per OS
- Oracle JDK cleanup glob patterns and safe-root validation roots
- Supported shells and their rc-file mappings
- Package-manager preference order, install/update/upgrade command
  templates (string form or argv-list form — argv preferred, see
  [`tools/shell.md`](tools/shell.md))
- UI colour mode and the back-label string
- Self-update toggle, github_repo for messaging
- The Homebrew install-script URL pin
- DNS recovery: test domains, DNS server profiles, step timeout,
  confirmation tokens for `reset` and `--nuclear`, backup directory
- AdGuard Home: install search paths, default remap ports, target
  ports list, safe-to-stop systemd units, `resolv_conf_mode`
  (symlink vs static), API-first preference, API base URL
- docker-clean: nuke-confirmation token, Kubernetes image patterns,
  daemon-verify timeout, default `buildx prune --all`

**Not configurable** (logic-critical, stay in code):

- The `# java-manager:openjdk@<v>` marker template in
  `ShellConfigWriter` — changing it would break idempotent re-writes
  of existing user rc files
- Regex patterns for parsing `java -version` and shell version output
- Atomic-replace semantics in the updater
- ANSI escape sequences themselves (just the toggle is configurable)

This split is intentional. See
[CONTRIBUTING.md](../CONTRIBUTING.md#architecture-rules) rule 4 for
the "what stays in code" criterion.

## Examples

### Force colour off

```bash
NO_COLOR=1 shimkit doctor
# or in shimkit.json:
{ "ui": { "color": "never" } }
```

### Add Java 22 support before defaults catch up

```json
{
  "tools": {
    "java": {
      "supported_versions": [
        { "major": 22, "label": "Current",     "brew_formula": "openjdk@22" },
        { "major": 21, "label": "LTS — Recommended", "brew_formula": "openjdk@21", "lts": true, "recommended": true },
        { "major": 17, "label": "LTS",         "brew_formula": "openjdk@17", "lts": true }
      ]
    }
  }
}
```

Note this replaces the whole list — include every version you want.

### Disable startup update check

```json
{ "self_update": { "check_on_startup": false } }
```

### Point self-update at a fork

```json
{ "self_update": { "github_repo": "alice/shimkit-fork" } }
```

### Use a different PM order on a hybrid system

```json
{
  "package_managers": {
    "preference_order": ["apt", "brew", "dnf"]
  }
}
```

### Pin a less aggressive DNS recovery profile

By default `shimkit dns fix` uses the `cloudflare` profile from
`tools.dns.dns_servers`. Override the available profiles or change
the test domains used to verify resolution:

```json
{
  "tools": {
    "dns": {
      "test_domains": ["example.com"],
      "dns_servers": {
        "cloudflare": ["1.1.1.1", "1.0.0.1"],
        "quad9":      ["9.9.9.9", "149.112.112.112"]
      },
      "nuclear_confirm_token": "I_REALLY_MEAN_IT"
    }
  }
}
```

Then: `shimkit dns fix --profile=quad9`.

### Tell `shimkit adguard fix` to keep `/etc/resolv.conf` static

The default is `symlink` (the AGH FAQ recommendation —
`/etc/resolv.conf -> /run/systemd/resolve/resolv.conf`). For
appliance-style hosts where the symlink is brittle, switch to a
static file:

```json
{
  "tools": {
    "adguard": {
      "resolv_conf_mode": "static",
      "prefer_api_over_yaml": false,
      "api_base_url": "http://127.0.0.1:3000"
    }
  }
}
```

### Strengthen the docker-clean `nuke` confirmation token

```json
{
  "tools": {
    "docker_clean": {
      "nuke_confirm_token": "DESTROY-DEV-ENV"
    }
  }
}
```

Then: `shimkit docker-clean nuke --confirm DESTROY-DEV-ENV`.
