"""Wrappers around macOS ``networksetup`` and ``route``.

Replaces the ``detect_service``/``detect_interface`` shell helpers in
the legacy script — those used ``grep -E '\\d'`` (Perl regex) which is
not supported by BSD ``grep``, so they silently failed on every macOS.
"""

from __future__ import annotations

import re

from shimkit.core import CommandRunner

from .models import NetworkService

_HW_HEADER_RE = re.compile(r"^Hardware Port:\s*(.+)$")
_HW_DEVICE_RE = re.compile(r"^Device:\s*(\S+)\s*$")
_DEFAULT_IF_RE = re.compile(r"^\s*interface:\s*(\S+)\s*$")


def list_hardware_ports() -> list[NetworkService]:
    """Return one :class:`NetworkService` per row of ``networksetup -listallhardwareports``."""
    r = CommandRunner.run(["networksetup", "-listallhardwareports"])
    if not r.ok:
        return []
    services: list[NetworkService] = []
    name: str | None = None
    for line in r.stdout.splitlines():
        if m := _HW_HEADER_RE.match(line):
            name = m.group(1).strip()
        elif (m := _HW_DEVICE_RE.match(line)) and name is not None:
            dev = m.group(1)
            services.append(
                NetworkService(
                    name=name,
                    device=dev,
                    is_wifi="Wi-Fi" in name or "Airport" in name,
                )
            )
            name = None
    return services


def default_interface() -> str | None:
    """Return the active default-route interface (e.g. ``en0``) or None."""
    r = CommandRunner.run(["route", "get", "default"])
    if not r.ok:
        return None
    for line in r.stdout.splitlines():
        if m := _DEFAULT_IF_RE.match(line):
            return m.group(1)
    return None


def active_service() -> NetworkService | None:
    """The :class:`NetworkService` for the active default-route interface."""
    dev = default_interface()
    if not dev:
        return None
    for s in list_hardware_ports():
        if s.device == dev:
            return s
    return None


def get_dns_servers(service: str) -> list[str]:
    """Return the configured DNS servers for ``service`` (empty if DHCP)."""
    r = CommandRunner.run(["networksetup", "-getdnsservers", service])
    if not r.ok:
        return []
    out = r.stdout.strip()
    if not out or "There aren't" in out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def set_dns_servers(service: str, servers: list[str]) -> bool:
    """Set DNS servers for ``service``; ``[]`` clears to DHCP."""
    from shimkit.core import sudo_prefix

    if not servers:
        cmd = [*sudo_prefix(), "networksetup", "-setdnsservers", service, "empty"]
    else:
        cmd = [*sudo_prefix(), "networksetup", "-setdnsservers", service, *servers]
    return CommandRunner.run(cmd).ok


def flush_cache() -> bool:
    """Run the canonical macOS DNS cache flush + mDNSResponder HUP."""
    from shimkit.core import sudo_prefix

    a = CommandRunner.run([*sudo_prefix(), "dscacheutil", "-flushcache"])
    b = CommandRunner.run([*sudo_prefix(), "killall", "-HUP", "mDNSResponder"])
    return a.ok and b.ok


def airport_power(device: str, on: bool) -> bool:
    """Toggle Wi-Fi power on ``device``. Caller must verify it's a Wi-Fi device."""
    from shimkit.core import sudo_prefix

    state = "on" if on else "off"
    r = CommandRunner.run([*sudo_prefix(), "networksetup", "-setairportpower", device, state])
    return r.ok
