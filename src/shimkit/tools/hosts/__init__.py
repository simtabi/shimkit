"""``/etc/hosts`` editor with atomic-write + backups — ``shimkit hosts``.

Add / remove / block / unblock individual entries, or apply a
StevenBlack-style block list. Every mutator writes through a temp
file (``install -m 644``) and creates a timestamped backup so
``shimkit hosts rollback`` restores cleanly.
"""

from __future__ import annotations

from .editor import Entry, HostsFile
from .manager import HostsManager

__all__ = ["Entry", "HostsFile", "HostsManager"]
