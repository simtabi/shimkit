from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.config import reset_cache
from shimkit.tools.java import (
    JavaInstallation,
    JavaVersion,
    OracleRemover,
)


def test_java_version_all_loaded_from_config() -> None:
    versions = JavaVersion.all()
    assert len(versions) == 5
    majors = {v.major for v in versions}
    assert majors == {8, 11, 17, 21, 24}
    v21 = JavaVersion.by_major(21)
    assert v21 is not None
    assert v21.lts is True
    assert v21.recommended is True
    assert v21.brew_formula == "openjdk@21"


def test_java_version_str_formatting() -> None:
    v = JavaVersion(major=21, label="LTS — Recommended", brew_formula="openjdk@21", lts=True)
    assert str(v) == "Java 21 (LTS — Recommended)"
    bare = JavaVersion(major=21, label="", brew_formula="openjdk@21")
    assert str(bare) == "Java 21"


def test_java_version_supports_config_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "shimkit.json"
    override.write_text(
        json.dumps(
            {
                "tools": {
                    "java": {
                        "default_version": 25,
                        "supported_versions": [
                            {
                                "major": 25,
                                "label": "Future",
                                "brew_formula": "openjdk@25",
                            }
                        ],
                    }
                }
            }
        )
    )
    monkeypatch.setenv("SHIMKIT_CONFIG", str(override))
    reset_cache()

    versions = JavaVersion.all()
    assert len(versions) == 1
    assert versions[0].major == 25


def test_java_installation_record() -> None:
    inst = JavaInstallation(kind="Homebrew", version="21", path="/opt/x", active=True)
    assert "active" in str(inst)
    assert "[Homebrew]" in str(inst)


def test_oracle_remover_unavailable_on_linux() -> None:
    from shimkit.core.platform import Platform

    r = OracleRemover(Platform(system="Linux", machine="x86_64"))
    assert r.available() is False
    assert r.remove() is False


def test_oracle_remover_patterns_expand_home() -> None:
    from shimkit.core.platform import Platform

    r = OracleRemover(Platform.detect())
    for p in r.patterns:
        assert not p.startswith("~"), f"unexpanded ~ in {p!r}"


# --- CLI integration --------------------------------------------------------


def test_cli_java_help_shows_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["java", "--help"])
    assert result.exit_code == 0
    for cmd in ("install", "list", "switch", "upgrade", "uninstall", "remove-oracle"):
        assert cmd in result.stdout


def test_cli_java_list_runs_without_brew_present(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force scan to find nothing — JavaManager.boot must succeed regardless.
    with patch("shimkit.tools.java.scanner.JavaScanner.scan", return_value=[]):
        result = runner.invoke(app, ["java", "list"])
    assert result.exit_code == 0


def test_cli_java_install_propagates_failure(
    runner: CliRunner,
) -> None:
    with patch("shimkit.tools.java.manager.JavaManager.install", return_value=False):
        result = runner.invoke(app, ["java", "install", "21"])
    assert result.exit_code == 1


def test_cli_java_install_propagates_success(
    runner: CliRunner,
) -> None:
    with patch("shimkit.tools.java.manager.JavaManager.install", return_value=True):
        result = runner.invoke(app, ["java", "install", "21"])
    assert result.exit_code == 0


def test_cli_java_install_no_arg_uses_config_default(runner: CliRunner) -> None:
    """`shimkit java install` (no version) should fall back to default_version."""
    with patch("shimkit.tools.java.manager.JavaManager.install", return_value=True) as m:
        result = runner.invoke(app, ["java", "install"])
    assert result.exit_code == 0
    m.assert_called_once_with("21")  # config default
