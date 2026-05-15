"""Port owner inspection + killer — ``shimkit ports``.

Cross-platform listing of which process holds each TCP/UDP port and a
prompted kill helper for stuck dev servers. ``lsof`` drives the macOS
path; ``ss`` drives the Linux path. No third-party deps.
"""

from __future__ import annotations

from .manager import PortsManager
from .models import PortOwner

__all__ = ["PortOwner", "PortsManager"]
