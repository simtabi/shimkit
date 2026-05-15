"""``shimkit cron`` -- generic user-crontab editor.

Add / list / remove shimkit-managed cron entries identified by a
``# shimkit:<name>`` comment immediately above the schedule line.
Atomic write via ``crontab <tempfile>``; backup-on-mutate.

The shimkit-managed comment is the marker; user-authored entries
are never touched. The tool's safety stance is the same as
``shimkit hosts``: the marker is what tells the tool "this line
is yours to manage".
"""

from __future__ import annotations

from .manager import CronManager
from .models import CronEntry

__all__ = ["CronEntry", "CronManager"]
