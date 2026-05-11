"""Config-layer exceptions."""

from __future__ import annotations


class ConfigError(Exception):
    """Raised when config cannot be loaded, parsed, or validated."""
