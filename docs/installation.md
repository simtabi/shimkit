# Installation

> **As of v0.2.2:** shimkit ships via the wheel + sdist attached to
> each [GitHub Release](https://github.com/simtabi/shimkit/releases).
> Publishing to PyPI is deferred — the trusted-publisher setup is in
> place on the GitHub side (`release.yml` + `pypi` environment) but
> the matching publisher on pypi.org is not configured yet, so the
> bare `pip install shimkit` / `uv tool install shimkit` /
> `pipx install shimkit` / `brew install simtabi/tap/shimkit`
> commands do not work yet. Use one of the install-from-source paths
> below until PyPI is wired up.

## Install from a release tag

```bash
# 1. Wheel from the GitHub Release page (works with any Python ≥ 3.10).
pip install --user \
  https://github.com/simtabi/shimkit/releases/download/v0.2.2/shimkit-0.2.2-py3-none-any.whl

# 2. Direct from a tag (no release-page step).
pip install --user git+https://github.com/simtabi/shimkit@v0.2.2
uv tool install   git+https://github.com/simtabi/shimkit@v0.2.2
pipx install      git+https://github.com/simtabi/shimkit@v0.2.2
```

## PyPI-style channels (pending)

These will become the primary install once PyPI trusted-publishing
is wired up:

```bash
uv tool install shimkit               # not yet — PyPI publishing pending
pipx install shimkit                  # not yet — PyPI publishing pending
pip install --user shimkit            # not yet — PyPI publishing pending
brew install simtabi/tap/shimkit      # not yet — tap depends on PyPI
```

## Version requirements

shimkit shells out to a handful of external binaries (docker, git,
gpg, nginx, ...). The minimum versions live in the JSON config
under `tools.versions`:

| Tool   | Minimum | Used by                                            |
|--------|--------:|----------------------------------------------------|
| docker | 20.10   | `docker-clean`, `db`, `stack`                      |
| nginx  | 1.20    | `web nginx vhost apply` (host path)                |
| git    | 2.30    | `gpg git-signing`                                  |
| gpg    | 2.2     | `gpg keys / agent / git-signing`                   |
| python | 3.10    | shimkit itself (enforced at install by `pyproject`)|

A missing or out-of-range tool causes the relevant subcommand's
`boot()` to exit with code **69 (EX_UNAVAILABLE)** and a
platform-specific install hint (`brew install <pkg>` on macOS;
`apt-get install <pkg>` on Linux).

Check the live state with `shimkit doctor`:

```
$ shimkit doctor
…
versions
  docker     28.5.2     ok
  nginx      1.27.2     ok
  git        2.51.0     ok
  gpg        2.4.9      ok
  python     3.12.7     ok
```

Override per-tool in `~/.config/shimkit/shimkit.json`:

```json
{
  "tools": {
    "versions": {
      "docker": {"min": "24.0", "max": "<26.0"},
      "nginx":  {"min": "1.18"}
    }
  }
}
```

Full spec:
[`.design/version-constraints-spec.md`](../.design/version-constraints-spec.md).

## Optional dependency extras

The base `shimkit` install is lean. The `java` and `shell` tools work
out of the box; the three newer tools each have an optional extra so
their dependencies (yaml, HTTP, psutil, docker-py, dnspython) only
land when you actually use them.

| Extra              | Pulls in                                  | Used by                |
|--------------------|-------------------------------------------|------------------------|
| `[dns]`            | `dnspython`                               | `shimkit dns verify` (optional precision) |
| `[adguard]`        | `ruamel.yaml`, `requests`, `psutil`       | `shimkit adguard` (Linux) |
| `[docker-clean]`   | `docker`                                  | `shimkit docker-clean` |
| `[extra-tools]`    | All of the above                          | Everything new         |

Install with an extra:

```bash
uv tool install 'shimkit[extra-tools]'
# or
pipx install 'shimkit[extra-tools]'
# or
pip install --user 'shimkit[extra-tools]'
```

Already installed and want to add an extra later:

```bash
uv tool install --upgrade 'shimkit[adguard]'
# or
pipx inject shimkit ruamel.yaml requests psutil
```

If you run a tool whose extra isn't installed, `shimkit` exits 69
with a message naming the exact install command for your platform.

## Verifying the install

```bash
shimkit version           # → 0.1.0
shimkit doctor            # platform + shell + PM + config validity
```

## Paranoid installs (verify the wheel)

Pin a specific release version and verify the wheel checksum against
the SBOM (`shimkit-sbom.spdx.json`) published alongside it:

```bash
release=0.2.0
pip download --no-deps "shimkit==${release}" -d /tmp
sha256sum /tmp/shimkit-${release}-py3-none-any.whl

# Then install from the local file:
pip install --user "/tmp/shimkit-${release}-py3-none-any.whl"
```

## <a id="updates"></a>Updates

`shimkit self-update` detects how shimkit was installed (`uv` /
`pipx` / `brew` / `pip`) and dispatches the matching upgrade command:

```bash
shimkit self-update           # prompts before upgrading
shimkit self-update -y        # non-interactive
```

It queries PyPI for the latest version. If it can't determine your
install method (you installed in some custom way), it prints the
direct install commands so you can reinstall manually.

Disable startup update checks via config (`config.self_update.check_on_startup`
= `false`) — see [Configuration](configuration.md).

## Uninstalling

```bash
uv tool uninstall shimkit                       # if installed via uv
pipx uninstall shimkit                          # if installed via pipx
pip uninstall shimkit                           # if installed via pip
brew uninstall simtabi/tap/shimkit              # if installed via brew

# Plus, optionally, clear the user config:
rm -rf ~/.config/shimkit/
```
