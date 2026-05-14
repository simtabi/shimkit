"""The 6-step DNS resolver recovery escalation.

Mirrors the ``fixdns.sh`` decision tree, with the bash bugs fixed:

* Step 4 (interface cycle): we check the active interface's hardware
  port before invoking ``-setairportpower``. The bash version did this
  unconditionally and silently no-op'd on Ethernet.
* Step 6 (nuclear): plist backups go to a config-driven backup dir
  under ``~/Library/Application Support/shimkit`` (not Desktop), and a
  rollback is offered. The user must pass the literal token from
  ``config.tools.dns.nuclear_confirm_token``.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from shimkit.config import get_config
from shimkit.core import CommandRunner, get_logger, sudo_prefix

from . import networksetup as ns
from .models import FixResult, FixStep

_LOG = get_logger("dns.fixer")


STEPS: tuple[FixStep, ...] = (
    FixStep(1, "flush", "Flush DNS cache + HUP mDNSResponder"),
    FixStep(2, "rebuild-resolver", "Toggle DNS servers (rebuild resolver config)"),
    FixStep(3, "uniform-dnssec", "Switch to a single uniform-DNSSEC provider"),
    FixStep(4, "cycle-interface", "Cycle the active network interface"),
    FixStep(5, "detect-vpn", "Detect Docker/Tailscale/VPN interference"),
    FixStep(6, "nuclear", "Regenerate SystemConfiguration plists (destructive)"),
)


_PLISTS_TO_BACKUP = (
    "/Library/Preferences/SystemConfiguration/preferences.plist",
    "/Library/Preferences/SystemConfiguration/NetworkInterfaces.plist",
    "/Library/Preferences/SystemConfiguration/com.apple.airport.preferences.plist",
)


def test_resolution(domain: str, timeout: float = 3.0) -> bool:
    """True iff ``domain`` resolves to at least one A/AAAA record.

    Pure Python — no shell-out, no dependency on ``timeout(1)`` which
    isn't on stock macOS.
    """
    original = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        infos = socket.getaddrinfo(domain, None)
        return bool(infos)
    except OSError:
        return False
    finally:
        socket.setdefaulttimeout(original)


def step_flush() -> FixResult:
    res = FixResult(step=STEPS[0])
    res.applied = ns.flush_cache()
    if res.applied:
        time.sleep(2)
        res.resolved = test_resolution("google.com")
    return res


def step_rebuild_resolver(service: str, servers: Sequence[str]) -> FixResult:
    """Toggle DNS servers OFF then ON — the real fix for Network.framework
    state corruption (per the writeups cited in docs/tools/dns.md)."""
    res = FixResult(step=STEPS[1])
    if not service:
        res.notes.append("No active network service detected.")
        return res
    if not ns.set_dns_servers(service, list(servers)):
        res.notes.append("Initial set_dns_servers failed.")
        return res
    time.sleep(1)
    if not ns.set_dns_servers(service, []):
        res.notes.append("Toggle-off failed.")
        return res
    time.sleep(1)
    if not ns.set_dns_servers(service, list(servers)):
        res.notes.append("Toggle-on failed.")
        return res
    ns.flush_cache()
    time.sleep(2)
    res.applied = True
    res.resolved = test_resolution("google.com")
    return res


def step_uniform_dnssec(service: str) -> FixResult:
    """Ventura+ prefers DNSSEC-capable servers in unpredictable ways when
    multiple providers are configured — collapsing to a single provider
    is the documented workaround."""
    res = FixResult(step=STEPS[2])
    if not service:
        res.notes.append("No active network service detected.")
        return res
    cf = get_config().tools.dns.dns_servers.get("cloudflare", ["1.1.1.1", "1.0.0.1"])
    if not ns.set_dns_servers(service, cf):
        res.notes.append("Failed to set Cloudflare-only DNS.")
        return res
    ns.flush_cache()
    time.sleep(2)
    res.applied = True
    res.resolved = test_resolution("google.com")
    if res.resolved:
        res.notes.append("Resolved with uniform DNSSEC (Cloudflare-only).")
    return res


def step_cycle_interface() -> FixResult:
    """Cycle the active interface — but ONLY power-cycle Wi-Fi when the
    active port is actually Wi-Fi (fixes the silent-no-op bug)."""
    res = FixResult(step=STEPS[3])
    service = ns.active_service()
    if service is None:
        res.notes.append("No active service detected.")
        return res

    if service.is_wifi:
        ok_off = ns.airport_power(service.device, on=False)
        time.sleep(3)
        ok_on = ns.airport_power(service.device, on=True)
        if not (ok_off and ok_on):
            res.notes.append("Airport power-cycle failed.")
            return res
        time.sleep(4)
    else:
        # Ethernet / USB: ifconfig down/up requires root.
        cmds = [
            [*sudo_prefix(), "ifconfig", service.device, "down"],
            [*sudo_prefix(), "route", "-n", "flush"],
            [*sudo_prefix(), "ifconfig", service.device, "up"],
        ]
        for c in cmds:
            if not CommandRunner.run(c).ok:
                res.notes.append(f"{' '.join(c)} failed.")
                return res
            time.sleep(2)

    ns.flush_cache()
    time.sleep(2)
    res.applied = True
    res.resolved = test_resolution("google.com")
    return res


def detect_interference() -> list[str]:
    """List likely DNS-corruption sources currently running.

    Common culprits documented in fixdns.sh and the writeups:
    Docker Desktop, OrbStack, Tailscale, any VPN with a utunN interface.
    """
    findings: list[str] = []
    candidates = ("Docker", "OrbStack", "Tailscale", "tailscaled")
    r = CommandRunner.run(["pgrep", "-x", *candidates])
    if r.ok and r.stdout.strip():
        # pgrep returns PIDs; we just need to know which were found.
        # Re-run per-name so the message is specific.
        for name in candidates:
            check = CommandRunner.run(["pgrep", "-x", name])
            if check.ok and check.stdout.strip():
                findings.append(f"{name} is running (common DNS corruption source)")

    ifconfig = CommandRunner.run(["ifconfig"])
    if ifconfig.ok:
        for line in ifconfig.stdout.splitlines():
            if line.startswith("utun") and "UP" in line:
                findings.append(f"VPN tunnel active: {line.split(':')[0]}")
                break
    return findings


def step_detect_vpn() -> FixResult:
    res = FixResult(step=STEPS[4])
    findings = detect_interference()
    res.applied = True
    res.notes.extend(findings)
    res.resolved = not findings and test_resolution("google.com")
    return res


def _make_backup_dir() -> Path:
    """Resolve the configured backup dir and refuse paths outside $HOME or /tmp.

    The default is under ``~/Library/Application Support/shimkit``. A
    malicious or fat-fingered config could point this at ``/etc`` or
    ``/var`` and we'd write under there as root. This guard rejects any
    path whose resolved location is not under the user's home or /tmp.
    """
    raw = Path(get_config().tools.dns.backup_dir).expanduser().resolve()
    home = Path.home().resolve()
    # /tmp is an explicit allow-listed root for tests / containers, not a
    # tempfile path we write to directly.
    tmp = Path("/tmp").resolve()  # nosec B108
    allowed_roots = (home, tmp)
    if not any(_is_within(raw, root) for root in allowed_roots):
        raise PermissionError(
            f"Refusing to write DNS backups outside HOME or /tmp: {raw}"
        )
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = raw / ts
    target.mkdir(parents=True, exist_ok=True)
    return target


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def step_nuclear() -> FixResult:
    """Regenerate SystemConfiguration plists — destructive last resort."""
    res = FixResult(step=STEPS[5])
    service = ns.active_service()
    if not service:
        res.notes.append("No active service — cannot proceed safely.")
        return res

    backup_dir = _make_backup_dir()
    res.notes.append(f"Plists backed up to {backup_dir}")

    for plist in _PLISTS_TO_BACKUP:
        src = Path(plist)
        if src.exists():
            CommandRunner.run(
                [*sudo_prefix(), "cp", "-a", str(src), str(backup_dir / src.name)],
                capture_output=False,
            )
            CommandRunner.run(
                [*sudo_prefix(), "rm", "-f", str(src)], capture_output=False
            )

    if service.is_wifi:
        ns.airport_power(service.device, on=False)
        time.sleep(3)
        ns.airport_power(service.device, on=True)
        time.sleep(5)
    else:
        # Best-effort interface cycle for non-Wi-Fi devices.
        CommandRunner.run([*sudo_prefix(), "ifconfig", service.device, "down"])
        time.sleep(2)
        CommandRunner.run([*sudo_prefix(), "ifconfig", service.device, "up"])
        time.sleep(4)

    ns.flush_cache()
    time.sleep(3)
    res.applied = True
    res.resolved = test_resolution("google.com")
    return res


def latest_backup_dir() -> Path | None:
    """Return the most recent ``dns-backups/<timestamp>/`` directory, or None."""
    root = Path(get_config().tools.dns.backup_dir).expanduser()
    if not root.is_dir():
        return None
    children = [c for c in root.iterdir() if c.is_dir()]
    if not children:
        return None
    return max(children, key=lambda p: p.stat().st_mtime)


def rollback() -> bool:
    """Restore plists from the most recent backup directory."""
    backup = latest_backup_dir()
    if not backup:
        _LOG.warning("No plist backup found for rollback.")
        return False
    ok = True
    for plist in _PLISTS_TO_BACKUP:
        name = Path(plist).name
        src = backup / name
        if src.exists():
            r = CommandRunner.run(
                [*sudo_prefix(), "cp", "-a", str(src), plist],
                capture_output=False,
            )
            if not r.ok:
                ok = False
    return ok
