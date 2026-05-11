"""Configuration layer.

Public API:
    get_config()        Cached, validated ShimkitConfig instance.
    load()              Force-reload, bypassing the cache.
    reset_cache()       Clear the cache (use between tests).
    user_config_path()  Path to ~/.config/shimkit/shimkit.json or override.
    bundled_defaults_path()  Path to defaults.json shipped with the package.
    ConfigError         Raised on parse or validation failure.

Schema:
    ShimkitConfig and child models live in shimkit.config.schema.
"""

from .errors import ConfigError
from .loader import (
    bundled_defaults_path,
    get_config,
    load,
    reset_cache,
    user_config_path,
)
from .schema import ShimkitConfig

__all__ = [
    "ConfigError",
    "ShimkitConfig",
    "bundled_defaults_path",
    "get_config",
    "load",
    "reset_cache",
    "user_config_path",
]
