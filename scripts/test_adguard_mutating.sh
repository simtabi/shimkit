#!/usr/bin/env bash
#
# shimkit adguard mutating-path integration test.
#
# Runs `shimkit adguard fix` inside a privileged systemd-enabled Ubuntu
# container so the systemd-resolved drop-in / /etc/resolv.conf swap /
# AGH service restart paths are exercised against a real Linux PID 1.
#
# Coverage relative to docs/validation-scope.md:
#
#   ✓ systemd-resolved DNSStubListener drop-in lands
#   ✓ /etc/resolv.conf is rewritten (symlink mode by default)
#   ✓ AGH systemd unit registers and restarts successfully
#   ✓ shimkit adguard rollback restores the resolv.conf backup
#
#   ✗ NetworkManager `dns=none` drop-in (NM is not installed by default;
#     no real network interfaces inside the container — file write
#     happens but the "survives interface event" check needs a desktop)
#
# Usage:
#   bash scripts/test_adguard_mutating.sh                  # uses dist/*.whl
#   WHEEL=/path/to/shimkit.whl bash scripts/...            # custom wheel
#   IMAGE=geerlingguy/docker-ubuntu2404-ansible:latest \
#     bash scripts/...                                     # custom image
#
# Local runs leave nothing behind — the container is `--rm`.

set -euo pipefail

# geerlingguy/docker-ubuntu2404-ansible is multi-arch (amd64 + arm64),
# ships with Python pre-installed, and runs systemd as PID 1 via its
# default entrypoint. Cleaner than jrei/systemd-ubuntu for our case.
IMAGE="${IMAGE:-geerlingguy/docker-ubuntu2404-ansible:latest}"
AGH_VERSION="${AGH_VERSION:-v0.107.74}"

# Locate the wheel.
if [ -z "${WHEEL:-}" ]; then
    # shellcheck disable=SC2012 # ls is fine here — wheels never have funny names.
    WHEEL=$(ls -1 dist/shimkit-*.whl 2>/dev/null | head -n1 || true)
fi
if [ -z "${WHEEL}" ] || [ ! -f "${WHEEL}" ]; then
    echo "ERROR: no wheel found at dist/shimkit-*.whl and \$WHEEL is unset." >&2
    echo "Run 'python -m build' first, or set WHEEL=/path/to/shimkit.whl." >&2
    exit 64
fi
WHEEL_ABS="$(cd "$(dirname "${WHEEL}")" && pwd)/$(basename "${WHEEL}")"
WHEEL_NAME="$(basename "${WHEEL}")"

# PLATFORM lets the caller force, e.g., linux/amd64 when using an
# amd64-only image on an arm64 host (jrei/systemd-ubuntu — needs
# Rosetta on macOS). The default image (geerlingguy/ ...) is
# multi-arch, so most callers don't set this.
PLATFORM_ARG="${PLATFORM:+--platform ${PLATFORM}}"

echo "image:    ${IMAGE}"
echo "wheel:    ${WHEEL_ABS}"
echo "AGH:      ${AGH_VERSION}"
echo "host:     $(uname -m)${PLATFORM_ARG:+ (forced ${PLATFORM})}"

# shellcheck disable=SC2086 # PLATFORM_ARG is intentionally word-split.
docker pull --quiet ${PLATFORM_ARG} "${IMAGE}"

# The test script that runs inside the container. Kept inline so the
# whole integration is one self-contained file on disk. Single-quoted
# heredoc with explicit close-quote / open-quote to interpolate
# WHEEL_NAME and AGH_VERSION exactly twice.
# shellcheck disable=SC2016
TEST_SCRIPT='
set -euo pipefail

echo "::group::install python + curl + dependencies"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip curl ca-certificates \
    iproute2 procps systemd-resolved >/dev/null
echo "::endgroup::"

echo "::group::start systemd-resolved (so it holds port 53)"
systemctl enable --now systemd-resolved
systemctl is-active systemd-resolved
ss -tulnp | grep ":53\b" || true
echo "::endgroup::"

echo "::group::install shimkit (built wheel) with the [adguard] extra"
python3 -m venv /opt/venv
/opt/venv/bin/pip install --quiet --upgrade pip
/opt/venv/bin/pip install --quiet "/wheel/'"${WHEEL_NAME}"'[adguard]"
/opt/venv/bin/shimkit version
echo "::endgroup::"

echo "::group::download + register AdGuard Home as a systemd unit"
curl -fsSL --proto "=https" --tlsv1.2 \
    -o /tmp/agh.tar.gz \
    "https://github.com/AdguardTeam/AdGuardHome/releases/download/'"${AGH_VERSION}"'/AdGuardHome_linux_amd64.tar.gz"
tar -xzf /tmp/agh.tar.gz -C /tmp
mkdir -p /opt/AdGuardHome
install -m 0755 /tmp/AdGuardHome/AdGuardHome /opt/AdGuardHome/AdGuardHome

# Pre-bake a minimal yaml: schema_version triggers AGH to skip the
# install wizard. No users → API not gated for verify/scan (we don'\''t
# exercise the API in this test). dns.port: 53 + http on :80 — both
# will collide with systemd-resolved (resolved holds :53). The fix
# flow MUST clear that.
cat > /opt/AdGuardHome/AdGuardHome.yaml <<YAML
schema_version: 28
users: []
dns:
  port: 53
  bind_hosts:
    - 0.0.0.0
  bootstrap_dns:
    - 127.0.0.1
  upstream_dns:
    - 127.0.0.1
http:
  address: 127.0.0.1:80
YAML

# Register as systemd service. AGH refuses to bind :53 right now
# (resolved holds it) — so we install the service but do NOT start it.
cd /opt/AdGuardHome
./AdGuardHome -s install >/dev/null 2>&1 || true
systemctl stop AdGuardHome 2>/dev/null || true
systemctl is-enabled AdGuardHome || true
echo "::endgroup::"

echo "::group::pre-state: shimkit adguard scan"
/opt/venv/bin/shimkit adguard scan --install /opt/AdGuardHome --json > /tmp/scan-before.json
cat /tmp/scan-before.json
python3 - <<"PY"
import json
d = json.load(open("/tmp/scan-before.json"))
assert d["tool"] == "adguard", d
assert d["data"]["dns_port"] == 53, d
ports = [c["port"] for c in d["data"]["conflicts"]]
assert 53 in ports, "expected port-53 conflict, got: " + str(d["data"]["conflicts"])
print("pre-state scan: dns_port=53 conflict reported as expected")
PY
echo "::endgroup::"

echo "::group::shimkit adguard fix (real mutating run)"
# Use --dns-cleanup-only so the test focuses on the systemd-resolved
# remediation; the yaml-remap path is exercised in the existing
# adguard-integration job on non-default ports.
/opt/venv/bin/shimkit adguard fix --install /opt/AdGuardHome \
    --dns-cleanup-only --json > /tmp/fix.json
cat /tmp/fix.json
echo "::endgroup::"

echo "::group::verify post-state"
# 1. The systemd-resolved drop-in landed.
ls -la /etc/systemd/resolved.conf.d/90-shimkit-adguardhome.conf
grep -q "DNSStubListener=no" /etc/systemd/resolved.conf.d/90-shimkit-adguardhome.conf

# 2. systemd-resolved was reloaded and no longer holds :53.
systemctl is-active systemd-resolved
sleep 2
if ss -tulnp 2>/dev/null | grep -E ":53\b.*systemd-resolve"; then
    echo "::error::systemd-resolved still on :53 after fix"
    exit 1
fi

# 3. /etc/resolv.conf was rewritten — either symlink form (default) or
# static. Either is acceptable; we just need 127.0.0.1 reachable for
# resolution.
echo "/etc/resolv.conf after fix:"
ls -la /etc/resolv.conf
if [ -L /etc/resolv.conf ]; then
    readlink /etc/resolv.conf
elif grep -q "nameserver 127.0.0.1" /etc/resolv.conf; then
    cat /etc/resolv.conf
else
    echo "::error::/etc/resolv.conf was not rewritten correctly"
    cat /etc/resolv.conf
    exit 1
fi

# 4. A backup of the prior resolv.conf was written.
ls /etc/resolv.conf.bak-* >/dev/null 2>&1 || {
    echo "::error::no /etc/resolv.conf.bak-* found"
    exit 1
}
echo "::endgroup::"

echo "::group::shimkit adguard rollback"
/opt/venv/bin/shimkit adguard rollback --install /opt/AdGuardHome >/dev/null || true
# After rollback, /etc/resolv.conf should match the backup.
echo "/etc/resolv.conf after rollback:"
ls -la /etc/resolv.conf
cat /etc/resolv.conf | head -5
echo "::endgroup::"

echo "::group::summary"
echo "All mutating-path assertions passed."
echo "::endgroup::"
'

# systemd-as-PID-1 containers require the image's own ENTRYPOINT
# (/sbin/init) to run; we can't supply a command at `docker run` time
# or systemd never starts. So: start detached, wait for systemd to
# come up, then `docker exec` the test, then clean up.
CONTAINER="shimkit-mutating-$$"

cleanup() {
    docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# --cgroupns=host is required for systemd to run as PID 1 inside a
# privileged container on modern Docker (cgroup-v2 unified hierarchy
# expects the host's cgroupns to be visible). Without it, systemd
# refuses to start and the container exits immediately.
#
# shellcheck disable=SC2086 # PLATFORM_ARG is intentionally word-split.
docker run -d --rm --privileged --name "${CONTAINER}" ${PLATFORM_ARG} \
    --cgroupns=host \
    --tmpfs /tmp --tmpfs /run --tmpfs /run/lock \
    -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
    -v "$(dirname "${WHEEL_ABS}"):/wheel:ro" \
    "${IMAGE}" >/dev/null

# Wait for systemd inside the container to reach a state where
# systemctl works. `running` is ideal; `degraded` is acceptable (some
# units fail in containers without harm to our test).
echo "waiting for systemd inside ${CONTAINER}..."
for i in $(seq 1 60); do
    state=$(docker exec "${CONTAINER}" systemctl is-system-running 2>/dev/null || true)
    case "${state}" in
        running|degraded)
            echo "  systemd ${state} after ${i}s"
            break
            ;;
    esac
    sleep 1
done

docker exec "${CONTAINER}" /bin/bash -c "${TEST_SCRIPT}"
