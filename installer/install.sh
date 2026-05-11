#!/bin/sh
# shimkit installer — one-liner bootstrap for end users.
#
#   curl -fsSL --proto '=https' --tlsv1.2 \
#     https://github.com/simtabi/shimkit/releases/latest/download/install.sh \
#     | sh
#
# Strategy: prefer uv (fast, isolated, modern), then pipx, then pip --user.
# Bootstraps uv on demand only when --with-uv is passed; never silently
# pulls a third-party install script.

set -eu

INFO()  { printf '%s\n' "shimkit-install: $*"; }
WARN()  { printf '%s\n' "shimkit-install: warning: $*" >&2; }
FAIL()  { printf '%s\n' "shimkit-install: error: $*" >&2; exit 1; }

PKG="shimkit"
WITH_UV=0
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --with-uv)
      WITH_UV=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      cat <<'EOF'
shimkit installer

Usage:
  install.sh [--with-uv] [--dry-run]

Options:
  --with-uv   If no installer is detected, fetch and install uv first.
              Adds an extra curl|sh step — use only if you trust uv's
              upstream installer (Astral signs their releases).
  --dry-run   Print what would happen, do nothing.
EOF
      exit 0
      ;;
    *)
      FAIL "unknown option: $1"
      ;;
  esac
done

run() {
  if [ "$DRY_RUN" = "1" ]; then
    INFO "would run: $*"
  else
    INFO "running:   $*"
    "$@"
  fi
}

check_python_310() {
  command -v python3 >/dev/null 2>&1 || return 1
  python3 - <<'PY' >/dev/null 2>&1
import sys
sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)
PY
}

if command -v uv >/dev/null 2>&1; then
  INFO "found uv — installing $PKG via uv tool"
  run uv tool install "$PKG"
  exit 0
fi

if command -v pipx >/dev/null 2>&1; then
  INFO "found pipx — installing $PKG via pipx"
  run pipx install "$PKG"
  exit 0
fi

if check_python_310; then
  INFO "found Python >=3.10 — installing $PKG via pip --user"
  run python3 -m pip install --user "$PKG"
  WARN "$PKG was installed to your user site. Make sure ~/.local/bin is on PATH."
  exit 0
fi

if [ "$WITH_UV" = "1" ]; then
  INFO "no installer found. Bootstrapping uv from upstream…"
  if [ "$DRY_RUN" = "1" ]; then
    INFO "would run: curl -fsSL --proto '=https' --tlsv1.2 https://astral.sh/uv/install.sh | sh"
  else
    curl -fsSL --proto '=https' --tlsv1.2 https://astral.sh/uv/install.sh | sh
  fi
  # uv installs into ~/.local/bin or ~/.cargo/bin depending on platform.
  for d in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [ -x "$d/uv" ]; then
      PATH="$d:$PATH"
      export PATH
      break
    fi
  done
  if command -v uv >/dev/null 2>&1; then
    INFO "uv bootstrapped — installing $PKG"
    run uv tool install "$PKG"
    INFO "Add this to your shell rc to keep uv on PATH:"
    INFO "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    exit 0
  fi
  FAIL "uv bootstrap finished but \`uv\` is still not on PATH"
fi

cat <<EOF >&2
$PKG could not be installed automatically — none of uv, pipx, or Python >=3.10
were found on this system.

Choose one and rerun:
  uv     (recommended)  https://docs.astral.sh/uv/getting-started/installation/
  pipx                  https://pipx.pypa.io/stable/installation/
  Python 3.10+          https://www.python.org/downloads/

Or rerun this installer with --with-uv to bootstrap uv automatically.
EOF
exit 1
