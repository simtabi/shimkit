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
    """Hermetic env + config cache + UI/logging state before every test."""
    from shimkit.core import UI
    from shimkit.core.log import reset_for_tests

    for var in ("SHIMKIT_CONFIG", "XDG_CONFIG_HOME", "NO_COLOR"):
        monkeypatch.delenv(var, raising=False)
    reset_cache()
    # Class-level UI flags persist across tests by default; reset them so
    # a test that sets --quiet / --no-color / --no-input doesn't bleed
    # into the next.
    UI.set_quiet(False)
    UI.set_color_mode(None)
    UI.set_no_input(False)
    reset_for_tests()
