# `shimkit shell` — shell upgrader

Upgrade `bash`, `zsh`, `fish`, or `ksh` via the host's native package
manager. Detects brew, apt, dnf, yum, pacman, apk, or zypper
automatically and dispatches the right install/upgrade commands. The
Python port of the original `butil-shell-upgrader`.

## Commands

| Command | What it does |
|---------|-------------|
| `shimkit shell` | Interactive menu |
| `shimkit shell info` | Platform, active shell, detected PM, installed shell versions |
| `shimkit shell upgrade NAME [--force]` | Upgrade `NAME` via the host PM. Prompts when `NAME` is the active shell (override with `--force`) |
| `shimkit shell simulate NAME` | Print the commands that would run, without executing |

## Typical flows

### What do I have?

```bash
$ shimkit shell info

Shell Info
  Platform        macOS (Apple Silicon)
  Active shell    zsh  →  /Users/me/.zshrc
  Package mgr     brew
  Installed shells:
    bash     5.3.3
    zsh      5.9
    fish     not installed
    ksh      not installed
```

Version detection runs `<shell> --version` and parses a semver-like
sequence from the output. Works for the standard bash/zsh/fish/ksh
output formats.

### Upgrading

```bash
shimkit shell upgrade zsh
```

If `zsh` is your active shell (likely), shimkit warns first:

```
⚠ zsh is your currently active shell. Upgrading it mid-session can
  leave you with broken builtins until you start a new terminal.
Continue upgrading zsh anyway? (y/N):
```

For scripted use (CI, automation runs from a spare terminal), skip
the prompt:

```bash
shimkit shell upgrade zsh --force
```

### Dry-running

```bash
$ shimkit shell simulate bash

Simulate: upgrade bash
[dry-run] brew update
[dry-run] brew upgrade bash
```

`simulate` resolves the rendered command from
`config.package_managers.definitions.<pm>.upgrade_cmd` without
running it.

## Configuration

```jsonc
{
  "tools": {
    "shell": {
      "supported_shells": ["bash", "zsh", "fish", "ksh"],
      "config_map": {
        "bash": { "rc_file": ".bash_profile", "fallback_rc": ".bashrc" },
        "zsh":  { "rc_file": ".zshrc" },
        "sh":   { "rc_file": ".profile" },
        "fish": { "rc_file": ".config/fish/config.fish" },
        "ksh":  { "rc_file": ".kshrc" }
      }
    }
  },
  "package_managers": {
    "preference_order": ["brew", "apt", "dnf", "yum", "pacman", "apk", "zypper"],
    "definitions": {
      "brew": {
        "install_cmd": "brew install ${pkg}",
        "update_cmd":  "brew update",
        "upgrade_cmd": "brew upgrade ${pkg}",
        "platforms":   ["macos", "linux"]
      },
      "apt": {
        "install_cmd": "apt-get install -y ${pkg}",
        "update_cmd":  "apt-get update",
        "upgrade_cmd": "apt-get install --only-upgrade -y ${pkg}",
        "platforms":   ["linux"]
      }
      // ... dnf, yum, pacman, apk, zypper
    }
  }
}
```

`${pkg}` is the only template variable. Sudo is prepended
automatically when needed (via `shimkit.core.command.sudo_prefix()`).

### Adding a custom shell

```json
{
  "tools": {
    "shell": {
      "supported_shells": ["bash", "zsh", "fish", "ksh", "elvish"],
      "config_map": {
        ...
        "elvish": { "rc_file": ".elvish/rc.elv" }
      }
    }
  }
}
```

### Different PM order on a hybrid host

```json
{
  "package_managers": {
    "preference_order": ["apt", "brew", "dnf"]
  }
}
```

On a Linux box with brew installed, this prefers `apt` over `brew`
for shell upgrades.

## Cross-PM dispatch

`PackageManager.detect(platform)` walks
`config.package_managers.preference_order` and returns the first PM:

- whose binary is on `$PATH` (`shutil.which`)
- whose `platforms` list includes the current OS key
  (`macos` / `linux`)

If nothing matches, `ShellManager.boot()` exits with a helpful error
pointing at `config.package_managers.preference_order`.

## Safety

- Active-shell guard before upgrade (skippable with `--force`).
- Sudo prefix auto-added when needed; omitted if already root or sudo
  is absent.
- `simulate` covers the "I'd like to see what happens first" workflow.

## Implementation pointers

- `src/shimkit/tools/shell/manager.py` — `ShellManager` orchestrator
- `src/shimkit/tools/shell/upgrader.py` — `ShellUpgrader` (version
  detection + dispatch)
- `src/shimkit/core/pkgmgr.py` — cross-PM `PackageManager` class
- `src/shimkit/core/shell.py` — `Shell` (rc-file detection with
  `fallback_rc`)

## Compatibility

- **macOS** (Apple Silicon + Intel): brew preferred
- **Linux**: brew if present, otherwise apt / dnf / yum / pacman /
  apk / zypper in config order
- **WSL** / Docker / LXC: same as native Linux
- **Windows** (native): not supported
