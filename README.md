# shimkit

A toolkit of developer utilities. Python tools, shimmed by bash.

```
$ shimkit --help
shimkit
  java          Manage OpenJDK installations.
  shell         Manage shell installations and upgrades.
  config        Inspect and edit shimkit configuration.
  doctor        Print system diagnostics useful for bug reports.
  self-update   Update shimkit itself to the latest release.
  version       Print the shimkit version.
```

## Install

```bash
curl -fsSL --proto '=https' --tlsv1.2 \
  https://github.com/simtabi/shimkit/releases/latest/download/install.sh \
  | sh
```

The installer prefers [`uv`](https://docs.astral.sh/uv/), then
[`pipx`](https://pipx.pypa.io/), then `pip --user` with Python 3.10+. Pass
`--with-uv` to bootstrap uv if none of those are present, or pick your
favourite directly:

```bash
uv tool install shimkit
pipx install shimkit
brew install simtabi/tap/shimkit          # once the tap is published
pip install --user shimkit                # Python 3.10+
```

For paranoid installs, verify the script's checksum first — see
[`installer/RELEASE.md`](installer/RELEASE.md) for the canonical recipe.

## Tools

### `shimkit java` — OpenJDK version manager

Install, switch, upgrade, uninstall, and remove Java versions on macOS and
Linux (including WSL and containers). Replaces the previous standalone
`java-update-manager` script.

```bash
shimkit java                  # interactive menu
shimkit java install 21       # direct
shimkit java list             # all discovered installations
shimkit java switch 17        # change active version
shimkit java upgrade          # upgrade every outdated openjdk@*
shimkit java uninstall 8
shimkit java remove-oracle    # macOS only
```

Supported versions, scan paths, and Oracle cleanup patterns are
configurable — see [Configuration](#configuration) below.

### `shimkit shell` — shell upgrader

Upgrade `bash` / `zsh` / `fish` / `ksh` via whichever package manager the
host provides (brew, apt, dnf, yum, pacman, apk, zypper).

```bash
shimkit shell                 # interactive menu
shimkit shell info            # platform + PM + per-shell version
shimkit shell upgrade bash
shimkit shell simulate bash   # dry-run print
```

### `shimkit config` — configuration

shimkit reads configuration from a layered chain:

1. Bundled defaults (inside the package — see `src/shimkit/config/defaults.json`).
2. User override at `~/.config/shimkit/shimkit.json` (or `$XDG_CONFIG_HOME`).
3. `$SHIMKIT_CONFIG=/abs/path` overrides the user path.
4. `NO_COLOR` forces colour off.

Inspect and edit:

```bash
shimkit config show                        # full resolved config
shimkit config show tools.java.default_version
shimkit config path                        # where the user file lives
shimkit config edit                        # opens $EDITOR; creates a stub if missing
shimkit config validate                    # lint defaults + override against the schema
```

Editor autocomplete: the user file's `$schema` key points at
[`config/shimkit.schema.json`](config/shimkit.schema.json), generated from
the pydantic models. Most editors with JSON Schema support will hint and
validate as you type.

### `shimkit doctor` — diagnostics

Prints platform, Python, and shell info — paste into bug reports.

### `shimkit self-update` — keep shimkit current

Detects how shimkit was installed (uv/pipx/brew/pip) and runs the matching
upgrade command. Looks up the latest version on PyPI; refuses to do
anything if it can't determine your install method (and prints the
one-liner for manual reinstall).

## Architecture

```
src/shimkit/
  cli.py              Top-level Typer dispatcher
  self_update.py      shimkit-itself upgrade flow
  config/             Layered JSON config + pydantic schema
  core/               Shared primitives — every tool depends on these
    command           CommandResult, CommandRunner — single subprocess chokepoint
    platform          OS / arch / WSL / container detection
    shell             Shell detection + idempotent rc-file writes
    pkgmgr            Cross-platform PackageManager (brew/apt/dnf/...)
    ui                Colour-aware terminal output (NO_COLOR-aware)
    menu              questionary wrapper with stdin fallback
  tools/
    java/             OpenJDK manager — JavaManager, JavaScanner, JavaInstaller, ...
    shell/            Shell upgrader — ShellManager, ShellUpgrader
```

Design rules:

- **Every tool builds on `shimkit.core` primitives.** No tool re-implements
  subprocess execution, OS detection, or shell rc-file writing.
- **`CommandRunner` is the single subprocess chokepoint.** Audit one place,
  not every tool.
- **Class-level constants live in `config/defaults.json`.** Logic-critical
  strings (idempotency markers, regexes) intentionally stay in code.
- **Builder pattern for orchestrators.** `JavaManager.create().boot().run()`,
  `ShellManager.create().boot().run()`. Same shape for every future tool.

## Configuration

The full schema is defined by pydantic models in `src/shimkit/config/schema.py`
and exported as JSON Schema at `config/shimkit.schema.json`. Headline keys:

```jsonc
{
  "ui": { "color": "auto", "icons": "auto", "spinner": "dots" },
  "self_update": {
    "enabled": true,
    "check_on_startup": true,
    "channel": "stable",
    "github_repo": "simtabi/shimkit"
  },
  "tools": {
    "java":  { "default_version": 21, "supported_versions": [...] },
    "shell": { "supported_shells": ["bash", "zsh", "fish", "ksh"] }
  },
  "package_managers": {
    "preference_order": ["brew", "apt", "dnf", "yum", "pacman", "apk", "zypper"],
    "definitions":      { /* install/update/upgrade templates per PM */ }
  }
}
```

User overrides are deep-merged on top of defaults. Lists are replaced
wholesale (a partial `supported_versions` override does not append).

## Development

```bash
git clone https://github.com/simtabi/shimkit
cd shimkit
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check src tests
mypy src/shimkit
```

Conventions live in [`CONTRIBUTING.md`](CONTRIBUTING.md). Releases are
tag-driven — see [`installer/RELEASE.md`](installer/RELEASE.md) for the
full ship checklist.

Distribution-channel setup guides:

- [`PYPI_SETUP.md`](PYPI_SETUP.md) — register `shimkit` on PyPI with
  OIDC trusted publishing
- [`DOCKER_SETUP.md`](DOCKER_SETUP.md) — multi-arch container image
  to GHCR and Docker Hub
- [`NPM_SETUP.md`](NPM_SETUP.md) — reference for future Node.js
  projects (shimkit itself is not on npm)

## Migration from `java-update-manager`

If you were using the standalone `java_update_manager.py` script, your
existing alias keeps working through the v2.x cycle: the script is now a
deprecation shim that forwards to `shimkit java`. Switch your alias to
`shimkit java` at your convenience; the shim is removed in v3.0.

## License

MIT — see [LICENSE](LICENSE).
