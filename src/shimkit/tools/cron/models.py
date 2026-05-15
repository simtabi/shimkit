"""Typed value objects for ``shimkit cron``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CronEntry:
    """One shimkit-managed cron entry.

    ``name``     is the slug used in the comment marker.
    ``schedule`` is the 5-field cron expression or a ``@``-shorthand.
    ``command``  is the rest of the line (everything after the
                 schedule whitespace).
    ``comment``  optional free-text comment from the user (stored on
                 the same line as the marker, e.g.
                 ``# shimkit:backup [daily DB dump]``).
    """

    name: str
    schedule: str
    command: str
    comment: str | None = None
