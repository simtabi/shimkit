"""Pure parsers for ``lsof`` (macOS) and ``ss`` (Linux) output.

Kept as pure string-in / list-of-PortOwner-out functions so they're
unit-testable without shelling out. The manager owns the
``CommandRunner.run`` calls and feeds their stdout into these.

Both parsers are tolerant of empty / malformed lines — a malformed
row is skipped, not raised, so a partial ``lsof`` output doesn't blow
up a probe that's only interested in a subset of ports.
"""

from __future__ import annotations

import re

from .models import PortOwner

# ─── macOS / lsof ──────────────────────────────────────────────────────────

# ``lsof -F pcnuP`` emits one field per line, prefixed by a single-char
# tag (``p``=pid, ``c``=command, ``u``=user, ``n``=name, ``P``=protocol).
# A process block opens with a ``p<pid>`` line and continues until the
# next ``p`` line; each file/socket inside the block opens with an ``f``
# line.
_LSOF_NAME_RE = re.compile(r"^(?P<addr>.*?):(?P<port>\d+)$")


def parse_lsof(output: str) -> list[PortOwner]:
    """Parse ``lsof -nP -iTCP -sTCP:LISTEN -iUDP -F pcnuP`` output."""
    owners: list[PortOwner] = []
    pid: int | None = None
    command: str | None = None
    user: str | None = None
    proto: str | None = None
    addr: str | None = None
    port: int | None = None

    def emit() -> None:
        nonlocal proto, addr, port
        if pid is None or command is None or proto is None or port is None:
            return
        owners.append(
            PortOwner(
                port=port,
                proto=proto.lower(),
                pid=pid,
                name=command,
                user=user,
                address=addr,
            )
        )
        # File-block fields reset; pid/command/user persist for the next
        # socket inside the same process block.
        proto = None
        addr = None
        port = None

    for raw in output.splitlines():
        if not raw:
            continue
        tag, _, value = raw[0], raw[1:2], raw[1:]
        del _
        if tag == "p":
            # New process block — emit any pending socket from the prior one.
            emit()
            pid = _maybe_int(value)
            command = None
            user = None
        elif tag == "c":
            command = value
        elif tag == "u":
            user = value
        elif tag == "f":
            # New socket — emit prior + reset socket-scoped fields.
            emit()
        elif tag == "P":
            proto = value
        elif tag == "n":
            # Names look like "*:80", "127.0.0.1:5432", "[::]:443".
            # Skip established connections that have an arrow (->).
            if "->" in value:
                addr = None
                port = None
                continue
            m = _LSOF_NAME_RE.match(value)
            if m:
                a = m.group("addr")
                addr = a if a not in ("", "*") else None
                port = int(m.group("port"))
    # Tail emit for the last socket in the stream.
    emit()
    return owners


# ─── Linux / ss ────────────────────────────────────────────────────────────

# ``ss -tulnpH`` rows look like:
#   tcp   LISTEN 0  511      0.0.0.0:80   0.0.0.0:*  users:(("nginx",pid=1234,fd=6))
#   udp   UNCONN 0  0   127.0.0.53%lo:53  0.0.0.0:*  users:(("systemd-resolve",pid=900,fd=12))
#
# Multiple processes can share a port; ss emits them comma-separated
# inside ``users:((...),(...))``. We surface each as its own PortOwner.
_SS_USER_RE = re.compile(r'\("(?P<name>[^"]+)",pid=(?P<pid>\d+),fd=(?P<fd>\d+)\)')


def parse_ss(output: str) -> list[PortOwner]:
    """Parse ``ss -tulnpH`` output."""
    owners: list[PortOwner] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        proto = parts[0].lower()
        # ``ss`` shows tcp LISTEN and udp UNCONN — we accept both.
        if proto not in {"tcp", "udp"}:
            continue
        local = parts[4]
        addr, port = _split_addr_port(local)
        if port is None:
            continue
        users_blob = line.split("users:", 1)[1] if "users:" in line else ""
        matches = _SS_USER_RE.findall(users_blob)
        if not matches:
            # Some kernels report "users:()" with no inner entries.
            owners.append(PortOwner(port=port, proto=proto, pid=0, name="?", address=addr))
            continue
        for name, pid_s, _fd in matches:
            owners.append(
                PortOwner(
                    port=port,
                    proto=proto,
                    pid=int(pid_s),
                    name=name,
                    address=addr,
                )
            )
    return owners


# ─── helpers ───────────────────────────────────────────────────────────────


def _maybe_int(s: str) -> int | None:
    try:
        return int(s)
    except ValueError:
        return None


def _split_addr_port(local: str) -> tuple[str | None, int | None]:
    """Split ``host:port`` or ``[::]:port`` or ``*:port``.

    ss may decorate the host with a scope (``127.0.0.53%lo``). The
    scope is preserved as part of the address.
    """
    # IPv6 with brackets: "[::]:443" → "::", 443
    if local.startswith("["):
        end = local.find("]")
        if end > 0 and local[end + 1 : end + 2] == ":":
            addr = local[1:end] or None
            try:
                port = int(local[end + 2 :])
            except ValueError:
                return None, None
            return addr, port
        return None, None
    # IPv4 / wildcard / hostname-style — split on the LAST colon so
    # IPv6 fragments without brackets (unlikely from ss but seen in
    # the wild) don't trip the split.
    idx = local.rfind(":")
    if idx < 0:
        return None, None
    addr = local[:idx] or None
    # Normalise wildcard-bind addresses from `ss` output to None so the
    # PortOwner.address is informational only. We're parsing, not binding.
    if addr in ("*", "0.0.0.0"):  # nosec B104 — string match on parser output, not a bind
        addr = None
    try:
        port = int(local[idx + 1 :])
    except ValueError:
        return None, None
    return addr, port


def filter_port(owners: list[PortOwner], port: int) -> list[PortOwner]:
    """Narrow a list of PortOwner to one port. Convenience for show/kill."""
    return [o for o in owners if o.port == port]
