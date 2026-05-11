"""Layered config loader.

Precedence (lowest → highest):
    1. Bundled defaults (src/shimkit/config/defaults.json)
    2. User override file (~/.config/shimkit/shimkit.json or $XDG_CONFIG_HOME)
    3. $SHIMKIT_CONFIG env (replaces user path entirely)
    4. NO_COLOR env var (forces ui.color = "never")

Result is validated against the pydantic schema. Validation failures point
at the offending JSONPath and refuse to run rather than silently using a
broken config.
"""

from __future__ import annotations

import functools
import json
import os
from copy import deepcopy
from importlib.resources import files
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .errors import ConfigError
from .schema import ShimkitConfig

USER_CONFIG_DIR = "shimkit"
USER_CONFIG_FILE = "shimkit.json"


def user_config_path() -> Path:
    """Resolve the path to the user override config file.

    Honors ``$SHIMKIT_CONFIG`` (absolute path) and ``$XDG_CONFIG_HOME``.
    Falls back to ``~/.config/shimkit/shimkit.json``.
    """
    override = os.environ.get("SHIMKIT_CONFIG")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / USER_CONFIG_DIR / USER_CONFIG_FILE


def bundled_defaults_path() -> Path:
    """Path to the package-bundled defaults.json. Useful for diagnostics."""
    return Path(str(files("shimkit.config") / "defaults.json"))


def _load_bundled_defaults() -> dict[str, Any]:
    text = (files("shimkit.config") / "defaults.json").read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


def _load_user_overrides(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except json.JSONDecodeError as e:
        raise ConfigError(
            f"Config file is not valid JSON: {path}\n"
            f"  line {e.lineno}, column {e.colno}: {e.msg}"
        ) from e


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base, returning a new dict.

    Lists are replaced wholesale (not concatenated) — predictable for
    things like supported_versions where partial overrides would surprise.
    """
    out = deepcopy(base)
    for key, value in override.items():
        if (
            isinstance(value, dict)
            and isinstance(out.get(key), dict)
        ):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _strip_meta(d: dict[str, Any]) -> dict[str, Any]:
    """Remove keys that are JSON-Schema metadata (e.g. ``$schema``)."""
    return {k: v for k, v in d.items() if not k.startswith("$")}


def _apply_env_overrides(d: dict[str, Any]) -> dict[str, Any]:
    """Apply minimal env-driven overrides.

    Currently supports:
        NO_COLOR — sets ui.color = "never" if set to any non-empty value.

    Generic ``SHIMKIT_*`` env mapping is intentionally deferred until there
    is a concrete need; YAGNI.
    """
    if os.environ.get("NO_COLOR"):
        ui = d.setdefault("ui", {})
        ui["color"] = "never"
    return d


def _format_validation_error(err: ValidationError, source_paths: list[Path]) -> str:
    parts = ["Configuration is invalid:"]
    for e in err.errors():
        loc = ".".join(str(p) for p in e["loc"])
        parts.append(f"  {loc}: {e['msg']}")
    parts.append("Sources merged (low → high precedence):")
    for p in source_paths:
        marker = "(exists)" if p.exists() else "(missing)"
        parts.append(f"  {p}  {marker}")
    return "\n".join(parts)


def load() -> ShimkitConfig:
    """Load the merged, validated config. Raises ``ConfigError`` on failure."""
    user = user_config_path()
    sources = [bundled_defaults_path(), user]

    raw = _load_bundled_defaults()
    raw = _strip_meta(raw)

    if user.exists():
        overrides = _strip_meta(_load_user_overrides(user))
        raw = _deep_merge(raw, overrides)

    raw = _apply_env_overrides(raw)

    try:
        return ShimkitConfig.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(_format_validation_error(e, sources)) from e


@functools.lru_cache(maxsize=1)
def get_config() -> ShimkitConfig:
    """Process-wide cached accessor. Use ``reset_cache()`` in tests."""
    return load()


def reset_cache() -> None:
    """Clear the cached config — call between tests that mutate env/files."""
    get_config.cache_clear()
