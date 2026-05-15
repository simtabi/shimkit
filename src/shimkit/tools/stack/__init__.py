"""``shimkit stack`` — multi-container app recipes.

One recipe today (``lemp``); the registry pattern lets new ones
(MERN, RAILS, MEAN) land as a single new module + a Typer
registration line.
"""

from __future__ import annotations

from .manager import StackManager

__all__ = ["StackManager"]
