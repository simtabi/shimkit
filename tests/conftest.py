"""Shared pytest fixtures.

The autouse ``_reset_env_and_config_cache`` fixture clears env vars that
influence config resolution (so tests are hermetic against the developer's
shell) and resets the cached pydantic config so each test sees fresh
defaults. Per-test overrides are still honoured — the fixture clears
*before* the test runs.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from shimkit.config import reset_cache


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def _reset_env_and_config_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hermetic env + config cache before every test."""
    for var in ("SHIMKIT_CONFIG", "XDG_CONFIG_HOME", "NO_COLOR"):
        monkeypatch.delenv(var, raising=False)
    reset_cache()
