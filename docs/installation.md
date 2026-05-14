# Installation

shimkit installs through whichever Python package manager you already
use. There is no curl-pipe-sh installer; use the channel that fits
your environment.

## Direct install methods

```bash
uv tool install shimkit               # fastest; per-tool isolated venv
pipx install shimkit                  # same isolation as uv
pip install --user shimkit            # Python ≥ 3.10
brew install simtabi/tap/shimkit      # once the tap is published
```

`uv tool install` is the recommended path. `pipx` is the close
second. `pip --user` works on any system with Python ≥ 3.10 but is
the most fragile because it shares your user-site with everything
else.

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

For the container image, `gh attestation verify` checks the
provenance signature published to GHCR alongside each tag.

## Container image

```bash
docker run --rm ghcr.io/simtabi/shimkit:latest version
docker run --rm -v "$HOME/.config/shimkit:/home/shimkit/.config/shimkit" \
  ghcr.io/simtabi/shimkit:latest doctor
```

Multi-arch (linux/amd64 + linux/arm64) is published per release.

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
