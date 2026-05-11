from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.config import (
    ConfigError,
    bundled_defaults_path,
    load,
    reset_cache,
    user_config_path,
)


def test_defaults_load_and_validate() -> None:
    cfg = load()
    assert cfg.schema_version == 1
    assert cfg.tools.java.default_version == 21
    formulae = {v.brew_formula for v in cfg.tools.java.supported_versions}
    assert {"openjdk@8", "openjdk@11", "openjdk@17", "openjdk@21", "openjdk@24"} <= formulae
    assert "bash" in cfg.tools.shell.config_map
    assert cfg.tools.shell.config_map["bash"].rc_file == ".bash_profile"
    assert cfg.package_managers.preference_order[0] == "brew"


def test_no_color_env_forces_color_never(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    reset_cache()
    cfg = load()
    assert cfg.ui.color == "never"


def test_user_override_via_shimkit_config_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "shimkit.json"
    override.write_text(
        json.dumps(
            {
                "tools": {
                    "java": {"default_version": 17}
                },
                "ui": {"color": "always"},
            }
        )
    )
    monkeypatch.setenv("SHIMKIT_CONFIG", str(override))
    reset_cache()
    cfg = load()
    assert cfg.tools.java.default_version == 17
    assert cfg.ui.color == "always"
    # Untouched defaults still present:
    assert len(cfg.tools.java.supported_versions) == 5


def test_invalid_json_raises_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "shimkit.json"
    bad.write_text("{not valid json")
    monkeypatch.setenv("SHIMKIT_CONFIG", str(bad))
    reset_cache()
    with pytest.raises(ConfigError) as ei:
        load()
    assert "not valid JSON" in str(ei.value)
    assert str(bad) in str(ei.value)


def test_invalid_schema_raises_pointing_at_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "shimkit.json"
    bad.write_text(json.dumps({"ui": {"color": "rainbow"}}))
    monkeypatch.setenv("SHIMKIT_CONFIG", str(bad))
    reset_cache()
    with pytest.raises(ConfigError) as ei:
        load()
    assert "ui.color" in str(ei.value)


def test_unknown_keys_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "shimkit.json"
    bad.write_text(json.dumps({"ui": {"colour": "auto"}}))  # typo
    monkeypatch.setenv("SHIMKIT_CONFIG", str(bad))
    reset_cache()
    with pytest.raises(ConfigError) as ei:
        load()
    assert "ui" in str(ei.value)


def test_dollar_schema_meta_key_is_stripped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "shimkit.json"
    override.write_text(json.dumps({"$schema": "https://example.com/schema.json"}))
    monkeypatch.setenv("SHIMKIT_CONFIG", str(override))
    reset_cache()
    # Should not raise even with an unknown $schema meta key.
    cfg = load()
    assert cfg.schema_version == 1


def test_xdg_config_home_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    reset_cache()
    expected = tmp_path / "shimkit" / "shimkit.json"
    assert user_config_path() == expected


def test_bundled_defaults_path_exists() -> None:
    assert bundled_defaults_path().exists()


# --- CLI integration --------------------------------------------------------


def test_cli_config_show_full(runner: CliRunner) -> None:
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["schema_version"] == 1
    assert parsed["tools"]["java"]["default_version"] == 21


def test_cli_config_show_dotted_section(runner: CliRunner) -> None:
    result = runner.invoke(app, ["config", "show", "ui.color"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == "auto"


def test_cli_config_show_unknown_section_fails(runner: CliRunner) -> None:
    result = runner.invoke(app, ["config", "show", "tools.nonexistent"])
    assert result.exit_code == 1


def test_cli_config_validate(runner: CliRunner) -> None:
    result = runner.invoke(app, ["config", "validate"])
    assert result.exit_code == 0
    assert "valid" in result.stdout.lower()


def test_cli_config_path(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHIMKIT_CONFIG", str(tmp_path / "x.json"))
    reset_cache()
    result = runner.invoke(app, ["config", "path"])
    assert result.exit_code == 0
    assert "defaults:" in result.stdout
    assert "user:" in result.stdout
