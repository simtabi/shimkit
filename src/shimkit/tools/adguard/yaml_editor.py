"""Round-trip-safe AGH YAML editor.

Uses ``ruamel.yaml`` instead of the bash awk indent-heuristic, so
comments and ordering are preserved across edits.

AGH's yaml has an asymmetry between the DNS port and the web UI port:

- ``dns.port: <int>`` is the canonical, stable key.
- ``http.address: "<host>:<port>"`` is the canonical web UI key in
  modern AGH (0.107.x). Older versions used ``http.port: <int>``;
  AGH's migration to schema_version 34 drops ``http.port`` and keeps
  only ``http.address``.

The read/write helpers below accept either form and write the
canonical one, so the round-trip is stable regardless of which form
the user (or a prior AGH startup) left in the file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _yaml() -> Any:
    """Lazy-load ruamel.yaml so the import only happens when the extra is present."""
    # `ruamel.yaml` is in the [adguard] extra; pyproject.toml
    # ignore_missing_imports handles CI where the extra isn't installed.
    from ruamel.yaml import YAML

    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 4096  # avoid line wrapping rewrites
    return y


def _parse_address_port(value: object) -> int | None:
    """Pull the port out of an ``http.address`` style ``"host:port"`` string."""
    if not isinstance(value, str) or ":" not in value:
        return None
    try:
        return int(value.rsplit(":", 1)[1])
    except ValueError:
        return None


def read_ports(path: Path) -> tuple[int | None, int | None]:
    """Return ``(dns_port, http_port)`` from the AGH yaml. Missing → None.

    ``http_port`` is read from ``http.address`` first (canonical AGH
    0.107.x form) and falls back to ``http.port`` for older configs.
    """
    y = _yaml()
    with path.open("r", encoding="utf-8") as f:
        doc = y.load(f) or {}

    dns_port: int | None = None
    if isinstance(doc.get("dns"), dict):
        v = doc["dns"].get("port")
        if isinstance(v, int):
            dns_port = v

    http_port: int | None = None
    if isinstance(doc.get("http"), dict):
        addr_port = _parse_address_port(doc["http"].get("address"))
        if addr_port is not None:
            http_port = addr_port
        else:
            v = doc["http"].get("port")
            if isinstance(v, int):
                http_port = v

    return dns_port, http_port


def set_ports(path: Path, *, dns: int | None, http: int | None) -> tuple[int | None, int | None]:
    """Atomically set the DNS and HTTP ports. Returns the new values.

    DNS is written to ``dns.port``. HTTP is written to ``http.address``
    (the canonical AGH 0.107.x form) preserving any existing host
    component. A legacy ``http.port`` key is left untouched if present;
    AGH will drop it on its next yaml rewrite.
    """
    y = _yaml()
    with path.open("r", encoding="utf-8") as f:
        doc = y.load(f) or {}

    if dns is not None:
        section = doc.setdefault("dns", {})
        section["port"] = int(dns)

    if http is not None:
        section = doc.setdefault("http", {})
        existing_addr = section.get("address")
        if isinstance(existing_addr, str) and ":" in existing_addr:
            host = existing_addr.rsplit(":", 1)[0]
        else:
            host = "0.0.0.0"  # nosec B104 - AGH defaults to listening on all interfaces
        section["address"] = f"{host}:{int(http)}"
        # Also update http.port when it's present in the file, so
        # consumers that haven't migrated yet stay consistent.
        if "port" in section:
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
