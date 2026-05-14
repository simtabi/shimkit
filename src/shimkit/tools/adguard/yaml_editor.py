"""Round-trip-safe AGH YAML editor.

Uses ``ruamel.yaml`` instead of the bash awk indent-heuristic, so
comments and ordering are preserved across edits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _yaml() -> Any:
    """Lazy-load ruamel.yaml so the import only happens when the extra is present."""
    from ruamel.yaml import YAML

    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 4096  # avoid line wrapping rewrites
    return y


def read_ports(path: Path) -> tuple[int | None, int | None]:
    """Return ``(dns.port, http.port)`` from the AGH yaml. Missing → None."""
    y = _yaml()
    with path.open("r", encoding="utf-8") as f:
        doc = y.load(f) or {}
    dns_port = doc.get("dns", {}).get("port") if isinstance(doc.get("dns"), dict) else None
    http_port = doc.get("http", {}).get("port") if isinstance(doc.get("http"), dict) else None
    return (
        int(dns_port) if isinstance(dns_port, int) else None,
        int(http_port) if isinstance(http_port, int) else None,
    )


def set_ports(path: Path, *, dns: int | None, http: int | None) -> tuple[int | None, int | None]:
    """Atomically set dns.port / http.port. Returns the new values."""
    y = _yaml()
    with path.open("r", encoding="utf-8") as f:
        doc = y.load(f) or {}
    if dns is not None:
        section = doc.setdefault("dns", {})
        section["port"] = int(dns)
    if http is not None:
        section = doc.setdefault("http", {})
        section["port"] = int(http)

    # Atomic write: tmpfile in same dir + os.replace.
    tmp = path.with_suffix(path.suffix + ".shimkit.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            y.dump(doc, f)
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return read_ports(path)
