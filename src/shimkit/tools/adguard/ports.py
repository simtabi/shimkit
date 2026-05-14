"""Port-conflict detection using psutil.

Replaces the ``ss``/``awk``/cgroup-v2 parsing in the bash script with
typed ``psutil.net_connections`` queries. The cgroup-v2 fallback is
still here for unit-name resolution, with the ``0::`` prefix preferred
(the unified-hierarchy line) over legacy multi-line cgroup files.
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import PortOwner

_UNIT_RE = re.compile(r"/([^/]+\.(?:service|scope))(?:/|$)")


def _pid_to_unit(pid: int, proc_root: Path | str = "/proc") -> str | None:
    """cgroup-v2-aware: prefer the line starting ``0::`` (unified).

    ``proc_root`` is injectable so tests can point at a tmpdir without
    needing to monkeypatch the global ``Path`` class.
    """
    cgroup = Path(proc_root) / str(pid) / "cgroup"
    if not cgroup.is_file():
        return None
    try:
        lines = cgroup.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    candidates: list[str] = []
    for ln in lines:
        # cgroup-v2 unified hierarchy: 0::/system.slice/foo.service
        if ln.startswith("0::"):
            m = _UNIT_RE.search(ln)
            if m:
                return m.group(1)
        else:
            m = _UNIT_RE.search(ln)
            if m:
                candidates.append(m.group(1))
    return candidates[0] if candidates else None


def owners_of(port: int, proto: str) -> list[PortOwner]:
    """Return processes listening on ``port`` over ``proto`` (tcp/udp)."""
    try:
        import psutil
    except ImportError:
        return []

    if proto == "tcp":
        kind = "tcp"
    elif proto == "udp":
        kind = "udp"
    else:
        return []

    out: list[PortOwner] = []
    try:
        conns = psutil.net_connections(kind=kind)
    except (psutil.AccessDenied, PermissionError):
        return []

    for c in conns:
        if c.laddr and getattr(c.laddr, "port", None) == port:
            # For TCP, we want only LISTEN; UDP has no LISTEN state.
            if proto == "tcp" and c.status != psutil.CONN_LISTEN:
                continue
            pid = c.pid or 0
            if pid <= 0:
                continue
            try:
                name = psutil.Process(pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                name = "?"
            out.append(PortOwner(pid=pid, name=name, unit=_pid_to_unit(pid)))
    return out


def is_agh_process(name: str) -> bool:
    """Tolerate the kernel's 15-char comm truncation."""
    return name == "AdGuardHome" or name.startswith("AdGuardHome")
