"""Typed events for ``--json`` output mode.

Every tool's ``--json`` command emits a single document on stdout:
either one :class:`Event` (for simple status commands) or a list of
events (for multi-step operations like ``adguard fix``).

All other chatter goes to stderr via :class:`shimkit.core.UI` — so
``shimkit foo --json | jq .`` always returns clean JSON.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EventStatus = Literal["ok", "warning", "error", "skipped", "info"]


class Event(BaseModel):
    """One step or observation emitted by a tool.

    The shape is intentionally generic so every tool can reuse it.
    ``data`` is a free-form payload for tool-specific detail; consumers
    should treat its keys as semi-stable.
    """

    model_config = ConfigDict(extra="forbid")

    ts: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC ISO-8601 timestamp.",
    )
    tool: str = Field(..., description="Top-level tool name, e.g. 'dns'.")
    step: str = Field(..., description="Step identifier, e.g. 'flush_cache'.")
    status: EventStatus = "ok"
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


def emit_json(events: Event | list[Event]) -> None:
    """Print a single JSON document to stdout and flush.

    ``--json`` mode emits exactly once per command invocation.
    """
    if isinstance(events, Event):
        payload: object = events.model_dump(mode="json")
    else:
        payload = [e.model_dump(mode="json") for e in events]
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    sys.stdout.flush()
