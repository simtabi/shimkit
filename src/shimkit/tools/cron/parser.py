"""Pure parser for crontab content.

Crontab content is line-oriented:

- Blank lines and ``#`` comment lines (without the shimkit marker)
  are user-authored noise; we preserve them verbatim on a round-trip.
- A shimkit-managed entry is a TWO-line block:

  ``# shimkit:<name>[ <free-text comment>]``
  ``<schedule> <command>``

  The marker comment must come IMMEDIATELY above the schedule line.
  If the schedule line is missing or malformed, the marker is
  preserved as a raw comment (we don't try to repair).
- Any other line is treated as raw user content.

This parser is pure: text-in / model-out, model-out / text. The
:class:`shimkit.tools.cron.manager.CronManager` owns the
``crontab -l`` / ``crontab <tempfile>`` shell-outs.
"""

from __future__ import annotations

import re

from .models import CronEntry

# Strict slug for the marker's <name> — same shape as docker
# container names + tool names elsewhere in shimkit.
_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")

# Crontab schedule: either 5 whitespace-separated fields OR a
# `@`-shorthand. The fields themselves can contain digits, `*`,
# commas, slashes, hyphens, and (for month/dow) three-letter names.
# We don't enforce numeric ranges -- cron itself validates that
# when the new file is loaded.
_SCHEDULE_AT_RE = re.compile(r"^@(reboot|yearly|annually|monthly|weekly|daily|hourly)$")
_SCHEDULE_FIELD_RE = re.compile(r"^[\dA-Za-z*,/\-]+$")


def is_valid_schedule(s: str) -> bool:
    """Cheap structural check. Cron is the authority on semantics.

    Accepts:

    - ``@reboot`` / ``@yearly`` / ``@annually`` / ``@monthly`` /
      ``@weekly`` / ``@daily`` / ``@hourly``.
    - Five whitespace-separated fields, each matching a permissive
      token regex (digits, ``*``, ``,``, ``/``, ``-``, and the
      three-letter month/day-of-week names).

    >>> is_valid_schedule("@daily")
    True
    >>> is_valid_schedule("0 3 * * *")
    True
    >>> is_valid_schedule("*/15 * * * *")
    True
    >>> is_valid_schedule("0 3 * * MON")
    True
    >>> is_valid_schedule("nope")
    False
    """
    s = s.strip()
    if not s:
        return False
    if s.startswith("@"):
        return bool(_SCHEDULE_AT_RE.match(s))
    parts = s.split()
    if len(parts) != 5:
        return False
    return all(_SCHEDULE_FIELD_RE.match(p) for p in parts)


def is_valid_name(name: str) -> bool:
    """``shimkit:<name>`` slug check. Lowercase, alnum + ``_-``,
    1-64 chars, must start with a letter.
    """
    return bool(_NAME_RE.match(name))


def parse(text: str, *, managed_prefix: str) -> tuple[list[str | CronEntry], list[CronEntry]]:
    """Parse a crontab body.

    Returns ``(items, entries)`` where:

    - ``items`` is the round-trip-preserving mixed list (raw strings
      for non-managed lines + :class:`CronEntry` instances for
      managed two-line blocks).
    - ``entries`` is the de-duplicated convenience view of just the
      :class:`CronEntry` objects, in disk order.
    """
    lines = text.splitlines()
    items: list[str | CronEntry] = []
    entries: list[CronEntry] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(managed_prefix):
            # Parse `# shimkit:<name>[ free-text]`
            tail = line[len(managed_prefix) :].strip()
            parts = tail.split(maxsplit=1)
            name = parts[0] if parts else ""
            comment = parts[1] if len(parts) > 1 else None
            # Require an immediately-following schedule line.
            sched_line = lines[i + 1] if i + 1 < len(lines) else ""
            sched_split = sched_line.strip().split(maxsplit=5)
            # Try 5-field first.
            if sched_line.strip().startswith("@"):
                bits = sched_line.strip().split(maxsplit=1)
                schedule = bits[0] if bits else ""
                command = bits[1] if len(bits) > 1 else ""
            elif len(sched_split) >= 6:
                schedule = " ".join(sched_split[:5])
                command = sched_split[5]
            else:
                schedule = ""
                command = ""
            if is_valid_name(name) and is_valid_schedule(schedule) and command:
                entry = CronEntry(
                    name=name,
                    schedule=schedule,
                    command=command,
                    comment=comment,
                )
                items.append(entry)
                entries.append(entry)
                i += 2
                continue
            # Marker without a parseable body — preserve verbatim.
            items.append(line)
            i += 1
            continue
        items.append(line)
        i += 1
    return items, entries


def render(items: list[str | CronEntry], *, managed_prefix: str) -> str:
    """Inverse of :func:`parse`. Preserves blank/comment/raw lines."""
    out: list[str] = []
    for it in items:
        if isinstance(it, str):
            out.append(it)
            continue
        # Render the marker comment, then the schedule + command.
        marker = managed_prefix + it.name
        if it.comment:
            marker += " " + it.comment
        out.append(marker)
        out.append(f"{it.schedule} {it.command}")
    return "\n".join(out) + ("\n" if out else "")
