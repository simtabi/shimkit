"""AdGuard Home port-conflict fixer — ``shimkit adguard``.

Ported from ``shell-scripts/fix-adguardhome-ports.sh``. The bash
version had several bugs and gaps that this port fixes:

* ran full DNS cleanup even when AGH was absent (could lose
  systemd-resolved with no replacement). Python exits 69 instead.
* awk-edited the AGH yaml even when AGH might be running, but the
  daemon overwrites yaml on shutdown (per the AGH wiki). Python stops
  AGH first and prefers the HTTP control API.
* only warned about NetworkManager clobbering ``/etc/resolv.conf``;
  this version writes the canonical ``dns=none`` drop-in.
* cgroup-v2-aware unit detection.
"""

from __future__ import annotations

from .manager import AdGuardManager
from .models import AdGuardInstall, PortConflict, PortOwner

__all__ = ["AdGuardInstall", "AdGuardManager", "PortConflict", "PortOwner"]
