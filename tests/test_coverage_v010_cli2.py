"""CLI-level coverage: doctor, config subcommands, version, self-update.

Tests run with stubbed network / external tools so they don't
depend on the host machine's state. Aimed at the cli.py module
plus a few thin top-level commands.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── shimkit version ──────────────────────────────────────────────────


def test_cli_version_prints_pkg_version(runner: CliRunner) -> None:
    from shimkit import __version__

    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_bare_prints_help(runner: CliRunner) -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Usage:" in result.output or "Commands" in result.output


# ─── shimkit config ──────────────────────────────────────────────────


def test_cli_config_show_full(runner: CliRunner) -> None:
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    # Output is JSON.
    doc = json.loads(result.output)
    assert "tools" in doc


def test_cli_config_show_section(runner: CliRunner) -> None:
    result = runner.invoke(app, ["config", "show", "tools.db"])
    assert result.exit_code == 0
    doc = json.loads(result.output)
    assert "default_port" in str(doc) or "engines" in doc


def test_cli_config_show_unknown_section(runner: CliRunner) -> None:
    result = runner.invoke(app, ["config", "show", "no.such.section"])
    assert result.exit_code == 1


def test_cli_config_path(runner: CliRunner) -> None:
    result = runner.invoke(app, ["config", "path"])
    assert result.exit_code == 0
    assert "defaults" in result.output


def test_cli_config_validate_ok(runner: CliRunner) -> None:
    result = runner.invoke(app, ["config", "validate"])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_cli_config_edit_creates_template(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """`config edit` creates the user template if missing, then EDITORs it."""
    from shimkit.config import reset_cache

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("EDITOR", "/bin/true")  # benign editor
    reset_cache()
    # Stub CommandRunner so we don't actually fork.
    monkeypatch.setattr(
        "shimkit.core.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(0, "", "")),
    )
    result = runner.invoke(app, ["config", "edit"])
    assert result.exit_code == 0
    # Template was created.
    from shimkit.config import user_config_path

    assert user_config_path().exists()


# ─── shimkit doctor ───────────────────────────────────────────────────


def test_cli_doctor_runs(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """doctor prints platform / shell / pm / config / install method / versions."""
    # Stub CommandRunner so the docker probe is quick.
    monkeypatch.setattr(
        "shimkit.core.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(0, "27.0.0\n", "")),
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "shimkit" in result.output
    assert "platform" in result.output.lower()
    assert "versions" in result.output.lower()


def test_cli_doctor_no_docker(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """When docker isn't on PATH, doctor still completes."""
    monkeypatch.setattr(
        "shimkit.cli._shutil.which" if False else "shutil.which",
        lambda b: None if b == "docker" else f"/usr/bin/{b}",
    )
    result = runner.invoke(app, ["doctor"])
    # Exit 0 regardless — doctor is read-only.
    assert result.exit_code == 0


# ─── shimkit self-update ──────────────────────────────────────────────


def test_cli_self_update_offline_returns_zero(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`self-update` should exit 0 when there's no update available."""
    from shimkit import self_update as _su

    class _Res:
        has_update = False
        method = None
        current = "0.9.0"
        latest = "0.9.0"

    monkeypatch.setattr(_su, "check", lambda: _Res())
    result = runner.invoke(app, ["self-update", "--yes"])
    # No update → exit 0.
    assert result.exit_code == 0


# ─── per-tool sub-app help ────────────────────────────────────────────


@pytest.mark.parametrize(
    "tool",
    [
        "java",
        "shell",
        "dns",
        "adguard",
        "docker-clean",
        "ports",
        "hosts",
        "ssh",
        "env",
        "gpg",
        "logs",
        "db",
        "stack",
        "web",
        "cron",
        "tls",
        "framework",
    ],
)
def test_cli_tool_help_works(runner: CliRunner, tool: str) -> None:
    """Every registered sub-app exposes --help cleanly."""
    result = runner.invoke(app, [tool, "--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output or "Commands" in result.output
