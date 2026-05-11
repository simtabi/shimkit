# `shimkit java` — OpenJDK version manager

Install, switch between, upgrade, uninstall, and clean up Java
versions. Works on macOS (Apple Silicon + Intel), Linux (incl. WSL,
Docker, LXC), and any other POSIX-ish environment with Homebrew.

## Commands

| Command | What it does |
|---------|-------------|
| `shimkit java` | Interactive menu (legacy java-update-manager UX) |
| `shimkit java install [VERSION]` | Install via Homebrew. `VERSION` defaults to `config.tools.java.default_version` |
| `shimkit java list` | List every discovered Java installation, marking the active one |
| `shimkit java switch VERSION` | `brew link --force openjdk@VERSION` + reload env |
| `shimkit java upgrade [VERSION]` | Upgrade a specific version, or every outdated `openjdk@*` when omitted |
| `shimkit java uninstall VERSION` | Remove the brew package + macOS JVM symlink + rc-file block |
| `shimkit java remove-oracle` | macOS only — clean up Oracle JDK artifacts |

Bare `shimkit java` invocation drops into the menu (preserves the
legacy UX). Subcommands skip the menu and exit with shell-friendly
codes.

## Typical flows

### First-time install on a clean machine

```bash
shimkit java install 21
```

The installer:

1. Bootstraps Homebrew if absent (`Brew.install_self()`).
2. Runs `brew update` then `brew install openjdk@21`.
3. On macOS: creates the system JVM symlink at
   `/Library/Java/JavaVirtualMachines/openjdk-21.jdk` (requires sudo).
4. Appends a marker block to your shell rc file:

   ```bash
   # java-manager:openjdk@21
   export PATH="/opt/homebrew/opt/openjdk@21/bin:$PATH"
   export JAVA_HOME="/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"
   ```

5. Reloads your shell environment in the current process so
   `java -version` works immediately.

### Switching the active version

```bash
shimkit java list
shimkit java switch 17
```

`switch` runs `brew link --force openjdk@17`, reloads env, and points
`$JAVA_HOME` at the newly linked version.

### Discovering what's installed

```bash
shimkit java list
```

Scans (deduplicated by real path):

- All Homebrew prefixes (Apple Silicon, Intel, Linuxbrew, per-user)
- `$JAVA_HOME` if set
- SDKman (`~/.sdkman/candidates/java/`)
- Container/CI image paths (`/opt/java`, `/opt/jdk`, `/opt/openjdk`)
- System JVM dirs (`/Library/Java/JavaVirtualMachines` on macOS,
  `/usr/lib/jvm` on Linux)

Scan paths come from `config.tools.java.scan_paths.{macos,linux,container}`.

### Removing Oracle JDK on macOS

```bash
shimkit java remove-oracle
```

Glob patterns from `config.tools.java.oracle_glob_patterns` are
validated against `oracle_safe_roots` before each `rm -rf` — paranoia
guard against a misconfigured glob deleting unrelated files.

## Configuration

```jsonc
{
  "tools": {
    "java": {
      "default_version": 21,
      "supported_versions": [
        { "major": 8,  "label": "Legacy",            "brew_formula": "openjdk@8",  "deprecated": true },
        { "major": 11, "label": "LTS",               "brew_formula": "openjdk@11", "lts": true },
        { "major": 17, "label": "LTS",               "brew_formula": "openjdk@17", "lts": true },
        { "major": 21, "label": "LTS — Recommended", "brew_formula": "openjdk@21", "lts": true, "recommended": true },
        { "major": 24, "label": "Current",           "brew_formula": "openjdk@24" }
      ],
      "scan_paths": {
        "macos":     ["/Library/Java/JavaVirtualMachines", "/opt/homebrew/opt", "/usr/local/opt"],
        "linux":     ["/usr/lib/jvm", "/usr/local/lib/jvm", "/usr/lib/jdk", "/home/linuxbrew/.linuxbrew/opt"],
        "container": ["/opt/java", "/opt/jdk", "/opt/openjdk"]
      },
      "oracle_glob_patterns": [...],
      "oracle_safe_roots":    [...]
    }
  }
}
```

Override any of these in `~/.config/shimkit/shimkit.json`. See
[Configuration](../configuration.md) for the layering rules.

### Adding a new Java version before defaults catch up

```json
{
  "tools": {
    "java": {
      "supported_versions": [
        { "major": 25, "label": "Current",     "brew_formula": "openjdk@25" },
        { "major": 21, "label": "LTS — Recommended", "brew_formula": "openjdk@21", "lts": true, "recommended": true },
        { "major": 17, "label": "LTS",         "brew_formula": "openjdk@17", "lts": true }
      ]
    }
  }
}
```

Note that lists replace wholesale — include every version you want.

## Idempotency

Re-running `shimkit java install 21` is safe. The rc-file marker
(`# java-manager:openjdk@21`) prevents duplicate `PATH` / `JAVA_HOME`
exports — second write is a no-op. Same logic protects `uninstall`:
removing a non-installed version is a no-op.

The marker template is **not** user-configurable — changing it would
break idempotent re-writes for existing rc files. See
[Configuration: what's not configurable](../configuration.md#whats-configurable-vs-not).

## Implementation pointers

- `src/shimkit/tools/java/manager.py` — `JavaManager` orchestrator
- `src/shimkit/tools/java/installer.py` — install/reinstall/uninstall/upgrade/switch
- `src/shimkit/tools/java/scanner.py` — multi-source discovery
- `src/shimkit/tools/java/oracle.py` — macOS Oracle cleanup
- `src/shimkit/tools/java/brew.py` — Homebrew operations
- `src/shimkit/tools/java/models.py` — `JavaVersion`, `JavaInstallation` dataclasses

## Compatibility

- **macOS** (Apple Silicon + Intel): full support, including JVM
  symlink management.
- **Linux** (Ubuntu, Fedora, Debian, Arch, Alpine, …): full support
  via Linuxbrew. System symlinks are macOS-only and skipped silently.
- **WSL** / Docker / LXC: detected via `Platform.is_wsl` /
  `Platform.is_container`; banner shows the tag. Same behaviour as
  native Linux.
- **Windows** (native): not supported. Use WSL.
