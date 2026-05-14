"""systemd-resolved + /etc/resolv.conf + NetworkManager remediation.

The bash version had three gaps:

1. The systemd-resolved drop-in path was correct but the rewrite of
   ``/etc/resolv.conf`` used the **static** form unconditionally. The
   AGH FAQ recommends the **symlink** form by default; we make it
   configurable via ``config.tools.adguard.resolv_conf_mode``.
2. NetworkManager would silently re-clobber ``/etc/resolv.conf`` on
   the next interface event. The script only warned. We write the
   canonical ``dns=none`` drop-in and reload NM.
3. The static file would orphan the user's existing nameservers. We
   back up the prior file first (atomic-rename style).
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from shimkit.core import CommandRunner, Systemd, get_logger, is_root, sudo_prefix

_LOG = get_logger("adguard.resolv")

_DROP_IN_UNIT = "systemd-resolved.service"
_DROP_IN_NAME = "90-shimkit-adguardhome.conf"
# The [Resolve] section is read from /etc/systemd/resolved.conf.d/,
# NOT from the service-unit drop-in dir. AGH FAQ #bindinuse documents
# this explicitly.
_DROP_IN_DIR = "/etc/systemd/resolved.conf.d"
_DROP_IN_BODY = """[Resolve]
# Managed by shimkit adguard fix — frees port 53 for AdGuard Home.
DNS=127.0.0.1
DNSStubListener=no
"""

_RESOLV = Path("/etc/resolv.conf")
_RESOLV_STATIC = """# Managed by shimkit adguard fix.
# Routes all glibc resolver lookups through AdGuard Home on 127.0.0.1.
nameserver 127.0.0.1
options edns0 trust-ad
"""

_NM_DROP_IN = Path("/etc/NetworkManager/conf.d/90-shimkit-adguardhome.conf")
_NM_BODY = """[main]
# Managed by shimkit adguard fix — keep NetworkManager from rewriting
# /etc/resolv.conf so AdGuard Home stays in charge of DNS.
dns=none
"""


def is_resolved_active() -> bool:
    return Systemd.is_active("systemd-resolved")


def is_nm_active() -> bool:
    return Systemd.is_active("NetworkManager")


def disable_resolved_stub() -> None:
    """Drop-in that disables the stub listener; reload-or-restart resolved.

    Writes to ``/etc/systemd/resolved.conf.d/`` (the [Resolve] config dir),
    NOT ``/etc/systemd/systemd-resolved.service.d/`` (which is for
    service-unit overrides). systemd-resolved reads its config from the
    former; a drop-in in the latter is silently ignored.
    """
    Systemd.write_drop_in(_DROP_IN_UNIT, _DROP_IN_NAME, _DROP_IN_BODY, target_dir=_DROP_IN_DIR)
    Systemd.daemon_reload()
    Systemd.reload_or_restart("systemd-resolved")


def write_resolv_symlink() -> bool:
    """The AGH FAQ-recommended path: symlink to /run/systemd/resolve/resolv.conf.

    Falls back to the static form if /run path doesn't exist, or if
    ``rm /etc/resolv.conf`` fails (container bind mounts).
    Returns True iff the resolv.conf was successfully replaced.
    """
    target = Path("/run/systemd/resolve/resolv.conf")
    if not target.exists():
        return write_resolv_static()
    _back_up_resolv()
    rm = CommandRunner.run([*sudo_prefix(), "rm", "-f", str(_RESOLV)], capture_output=True)
    if not rm.ok:
        # `/etc/resolv.conf` is bind-mounted in many container runtimes
        # (Docker, Podman) — rm fails with EBUSY. Fall through to the
        # static-overwrite path which writes through the existing fd.
        _LOG.warning(
            "Could not rm /etc/resolv.conf (%s); falling back to static form.",
            rm.stderr.strip() or "EBUSY?",
        )
        return write_resolv_static()
    ln = CommandRunner.run(
        [*sudo_prefix(), "ln", "-sf", str(target), str(_RESOLV)],
        capture_output=True,
    )
    return ln.ok


def write_resolv_static() -> bool:
    """Static /etc/resolv.conf pointing at 127.0.0.1 (AGH).

    Returns True iff the file was successfully written.

    Try `sudo install` first (atomic replace, correct on real hosts).
    If that fails (typically because /etc/resolv.conf is a bind mount
    in container runtimes, where the inode can't be replaced), fall
    through to a Python direct-write that overwrites the file's
    content through the existing inode — bind-mount-friendly.
    """
    _back_up_resolv()
    import tempfile

    fd, tmp = tempfile.mkstemp(prefix="shimkit-resolv-", suffix=".conf")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_RESOLV_STATIC)
        r = CommandRunner.run(
            [
                *sudo_prefix(),
                "install",
                "-m",
                "0644",
                "-o",
                "root",
                tmp,
                str(_RESOLV),
            ],
            capture_output=True,
        )
        if r.ok:
            return True

        # Fall back: write content through the existing inode. Works on
        # bind-mounted /etc/resolv.conf (containers); requires root.
        if is_root():
            try:
                _RESOLV.write_text(_RESOLV_STATIC, encoding="utf-8")
                return True
            except OSError as exc:
                _LOG.warning("Direct write to %s failed: %s", _RESOLV, exc)
        else:
            _LOG.warning(
                "install of %s failed (%s) and not root for direct fallback.",
                _RESOLV,
                r.stderr.strip() or "?",
            )
        return False
    finally:
        Path(tmp).unlink(missing_ok=True)


def _back_up_resolv() -> Path | None:
    if not (_RESOLV.exists() or _RESOLV.is_symlink()):
        return None
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    bak = Path(f"/etc/resolv.conf.bak-{ts}")
    CommandRunner.run(
        [*sudo_prefix(), "cp", "-aL", str(_RESOLV), str(bak)],
        capture_output=False,
    )
    return bak


def configure_network_manager() -> bool:
    """Tell NM to stop managing /etc/resolv.conf. Idempotent.

    Returns True iff NM was active and the drop-in was successfully
    written + reloaded. Returns False (without raising) when NM is
    inactive — that's a no-op, not a failure.
    """
    if not is_nm_active():
        return False
    import tempfile

    fd, tmp = tempfile.mkstemp(prefix="shimkit-nm-", suffix=".conf")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_NM_BODY)
        r = CommandRunner.run(
            [
                *sudo_prefix(),
                "install",
                "-m",
                "0644",
                "-o",
                "root",
                tmp,
                str(_NM_DROP_IN),
            ],
            capture_output=True,
        )
        if not r.ok:
            return False
    finally:
        Path(tmp).unlink(missing_ok=True)
    reload = CommandRunner.run([*sudo_prefix(), "nmcli", "general", "reload"], capture_output=True)
    return reload.ok


def latest_resolv_backup() -> Path | None:
    candidates = sorted(Path("/etc").glob("resolv.conf.bak-*"))
    return candidates[-1] if candidates else None
