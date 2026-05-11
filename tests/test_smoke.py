from __future__ import annotations

from typer.testing import CliRunner

from shimkit import __version__
from shimkit.cli import app


def test_version_command_prints_version(runner: CliRunner) -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_doctor_command_runs(runner: CliRunner) -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "shimkit" in result.stdout
    assert "python" in result.stdout


def test_help_lists_all_top_level_commands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("java", "shell", "config", "doctor", "self-update", "version"):
        assert cmd in result.stdout
