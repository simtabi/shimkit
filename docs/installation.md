# Installation

## One-liner

```bash
curl -fsSL --proto '=https' --tlsv1.2 \
  https://github.com/simtabi/shimkit/releases/latest/download/install.sh \
  | sh
```

The installer prefers, in order:

1. **uv** (`uv tool install shimkit`) — fastest, isolated venv per tool
2. **pipx** (`pipx install shimkit`) — same isolation as uv, slightly
   slower start-up
3. **pip --user** (`python3 -m pip install --user shimkit`) — requires
   Python ≥ 3.10 on `$PATH`

Pass `--with-uv` to bootstrap uv if none of the three is present:

```bash
curl -fsSL ... | sh -s -- --with-uv
```

`--dry-run` prints the chosen path without executing it.

## Direct install methods

If you already use one of these tools:

```bash
uv tool install shimkit
pipx install shimkit
pip install --user shimkit            # Python ≥ 3.10
brew install simtabi/tap/shimkit      # once the tap is published
```

## Verifying the install

```bash
shimkit version           # → 0.1.0
shimkit doctor            # platform + shell + PM + config validity
```

## Paranoid installs (verify the installer)

Pin the release tag and verify the SHA256:

```bash
release=v0.1.0
base=https://github.com/simtabi/shimkit/releases/download/${release}
curl -fsSL --proto '=https' --tlsv1.2 "${base}/install.sh"        -o install.sh
curl -fsSL --proto '=https' --tlsv1.2 "${base}/install.sh.sha256" -o install.sh.sha256
sha256sum -c install.sh.sha256
sh install.sh
```

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
canonical one-liner so you can reinstall manually.

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
