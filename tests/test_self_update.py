from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

from shimkit import __version__
from shimkit import self_update as su
from shimkit.cli import app
from shimkit.config import reset_cache
from shimkit.core import CommandResult

# --- pure helpers ----------------------------------------------------------


def test_parse_strips_v_prefix() -> None:
    assert su._parse("v1.2.3") == (1, 2, 3)
    assert su._parse("0.1.0") == (0, 1, 0)
    assert su._parse("garbage") == (0,)


def test_update_check_result_has_update() -> None:
    older = su.UpdateCheckResult(current="0.1.0", latest="0.2.0", method="uv")
    same = su.UpdateCheckResult(current="0.1.0", latest="0.1.0", method="uv")
    none = su.UpdateCheckResult(current="0.1.0", latest=None, method="uv")
    assert older.has_update is True
    assert same.has_update is False
    assert none.has_update is False


def test_install_commands_lists_direct_methods() -> None:
    cmds = su.install_commands()
    assert any(c.startswith("uv tool install") for c in cmds)
    assert any(c.startswith("pipx install") for c in cmds)
    assert any(c.startswith("pip install --user") for c in cmds)
    assert any(c.startswith("brew install") for c in cmds)


# --- detect ---------------------------------------------------------------


def _stub_run(stdout_for: dict[tuple[str, ...], str]) -> Any:
    """Return a fake CommandRunner.run that maps argv prefixes to stdout."""

    def fake(cmd, **_):  # type: ignore[no-untyped-def]
        argv = tuple(cmd) if isinstance(cmd, list) else (cmd,)
        for prefix, out in stdout_for.items():
            if argv[: len(prefix)] == prefix:
                return CommandResult(0, out, "")
        return CommandResult(1, "", "not found")

    return fake


def test_detect_uv_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "shimkit.self_update.CommandRunner.run",
        _stub_run({("uv", "tool", "list"): "shimkit v0.1.0\nruff v0.9.0"}),
    )
    assert su._detect_install_method() == "uv"


def test_detect_pipx_when_uv_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "shimkit.self_update.CommandRunner.run",
        _stub_run({("pipx", "list", "--short"): "shimkit 0.1.0"}),
    )
    assert su._detect_install_method() == "pipx"


def test_detect_brew_after_pipx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "shimkit.self_update.CommandRunner.run",
        _stub_run({("brew", "list", "--formula"): "shimkit\nsqlite"}),
    )
    assert su._detect_install_method() == "brew"


def test_detect_returns_none_when_nothing_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "shimkit.self_update.CommandRunner.run",
        lambda *a, **kw: CommandResult(1, "", "no"),
    )
    assert su._detect_install_method() is None


# --- run flow --------------------------------------------------------------


def test_run_when_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    override = tmp_path / "shimkit.json"
    override.write_text(json.dumps({"self_update": {"enabled": False}}))
    monkeypatch.setenv("SHIMKIT_CONFIG", str(override))
    reset_cache()

    rc = su.run(yes=True)
    assert rc == 0


def test_run_when_no_pypi_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.self_update._latest_pypi_version", lambda: None)
    rc = su.run(yes=True)
    assert rc == 1


def test_run_when_already_up_to_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "shimkit.self_update._latest_pypi_version", lambda: __version__
    )
    rc = su.run(yes=True)
    assert rc == 0


def test_run_when_no_install_method(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.self_update._latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr("shimkit.self_update._detect_install_method", lambda: None)
    rc = su.run(yes=True)
    assert rc == 2


def test_run_dispatches_uv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.self_update._latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr("shimkit.self_update._detect_install_method", lambda: "uv")
    seen: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr("shimkit.self_update.CommandRunner.run", fake_run)
    rc = su.run(yes=True)
    assert rc == 0
    assert seen == [["uv", "tool", "upgrade", "shimkit"]]


# --- CLI -------------------------------------------------------------------


def test_cli_self_update_passes_yes_flag(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[bool] = []

    def fake_run(yes: bool) -> int:
        seen.append(yes)
        return 0

    monkeypatch.setattr("shimkit.self_update.run", fake_run)
    result = runner.invoke(app, ["self-update", "-y"])
    assert result.exit_code == 0
    assert seen == [True]
