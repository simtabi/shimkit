"""Minimal client for the AdGuard Home HTTP control API.

The full OpenAPI spec lives at:
  https://github.com/AdguardTeam/AdGuardHome/blob/master/openapi/openapi.yaml

We only call the endpoints we need:

* ``GET /control/status`` — health + version probe (no auth).
* ``POST /control/install/configure`` — set DNS/web ports.

Auth (HTTP Basic) is read from env vars ``ADGUARD_USER`` /
``ADGUARD_PASS``. Never accepted as CLI flags.
"""

from __future__ import annotations

import os
from typing import Any

from shimkit.config import get_config


def _auth() -> tuple[str, str] | None:
    user = os.environ.get("ADGUARD_USER")
    pwd = os.environ.get("ADGUARD_PASS")
    if user and pwd:
        return (user, pwd)
    return None


def _base() -> str:
    return get_config().tools.adguard.api_base_url.rstrip("/")


def status(timeout: float = 5.0) -> dict[str, Any] | None:
    """Return ``/control/status`` or None on any error."""
    try:
        import requests
    except ImportError:
        return None
    try:
        r = requests.get(
            f"{_base()}/control/status",
            auth=_auth(),
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        data: dict[str, Any] = r.json()
        return data
    except Exception:
        return None


def set_ports(*, dns_port: int, http_port: int, timeout: float = 10.0) -> bool:
    """Set DNS/web ports via the API. Requires HTTP Basic auth.

    Uses ``/control/install/configure``, which expects a full payload —
    we read the current bind addresses from ``/control/status`` to
    preserve them.
    """
    try:
        import requests
    except ImportError:
        return False
    s = status(timeout=timeout)
    if s is None:
        return False
    # /control/install/configure expects "web" + "dns" sections per OpenAPI.
    # 0.0.0.0 (bind on all interfaces) is the standard for AGH on a LAN — the
    # whole point of running a DNS resolver is for clients to reach it.
    payload: dict[str, Any] = {
        "web": {"ip": "0.0.0.0", "port": http_port, "autofix": False},  # nosec B104
        "dns": {"ip": "0.0.0.0", "port": dns_port, "autofix": False},  # nosec B104
    }
    try:
        r = requests.post(
            f"{_base()}/control/install/configure",
            json=payload,
            auth=_auth(),
            timeout=timeout,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False


def is_reachable(timeout: float = 3.0) -> bool:
    return status(timeout=timeout) is not None
