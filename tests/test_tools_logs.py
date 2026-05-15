"""Tests for ``shimkit logs``.

The tool itself is read-only and platform-dispatched — most assertions
are about which argv list lands in ``CommandRunner.run``. The
``--json`` mode is exercised because it bypasses the shell-out and
emits an Event whose `data.args` field captures intent without
mocking everything in capture_output=False mode.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult
from shimkit.core.platform import Platform
from shimkit.tools.logs.manager import LogsManager


def _force_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.tools.logs.manager.shutil.which", lambda _: "/usr/bin/journalctl")


def _force_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Darwin", machine="arm64")),
    )
    monkeypatch.setattr("shimkit.tools.logs.manager.shutil.which", lambda _: "/usr/bin/log")


# ─── platform / binary gating ───────────────────────────────────────────


def test_boot_exits_69_on_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Windows", machine="x86_64")),
    )
    with pytest.raises(SystemExit) as exc:
        LogsManager.create().boot()
    assert exc.value.code == 69


def test_boot_exits_69_when_journalctl_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.tools.logs.manager.shutil.which", lambda _: None)
    with pytest.raises(SystemExit) as exc:
        LogsManager.create().boot()
    assert exc.value.code == 69


def test_boot_exits_69_when_log_missing_on_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Darwin", machine="arm64")),
    )
    monkeypatch.setattr("shimkit.tools.logs.manager.shutil.which", lambda _: None)
    with pytest.raises(SystemExit) as exc:
        LogsManager.create().boot()
    assert exc.value.code == 69


# ─── tail ───────────────────────────────────────────────────────────────


def test_logs_tail_emits_journalctl_argv_on_linux(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    result = runner.invoke(app, ["logs", "tail", "--lines", "50", "--unit", "sshd", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["platform"] == "Linux"
    args = doc["data"]["args"]
    assert args[0] == "journalctl"
    assert "-n" in args and "50" in args
    assert "-u" in args and "sshd" in args
    assert doc["data"]["follow"] is False


def test_logs_tail_follow_uses_log_stream_on_macos(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_macos(monkeypatch)
    result = runner.invoke(app, ["logs", "tail", "--follow", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["platform"] == "Darwin"
    args = doc["data"]["args"]
    # macOS follow mode uses `log stream`, not `log show`.
    assert args[:2] == ["log", "stream"]


def test_logs_tail_follow_adds_minus_f_on_linux(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    result = runner.invoke(app, ["logs", "tail", "--follow", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert "-f" in doc["data"]["args"]


def test_logs_tail_predicate_passes_through_on_macos(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_macos(monkeypatch)
    pred = 'process == "kernel"'
    result = runner.invoke(app, ["logs", "tail", "--predicate", pred, "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    args = doc["data"]["args"]
    assert "--predicate" in args
    idx = args.index("--predicate")
    assert args[idx + 1] == pred


def test_logs_tail_predicate_becomes_grep_on_linux(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    result = runner.invoke(app, ["logs", "tail", "--predicate", "ERROR", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    args = doc["data"]["args"]
    assert "--grep" in args and "ERROR" in args


def test_logs_tail_invokes_command_runner_in_non_json_mode(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    captured: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        captured.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr("shimkit.tools.logs.manager.CommandRunner.run", staticmethod(fake_run))
    result = runner.invoke(app, ["logs", "tail"])
    assert result.exit_code == 0
    assert captured and captured[0][0] == "journalctl"


# ─── grep ───────────────────────────────────────────────────────────────


def test_logs_grep_uses_eventmessage_contains_on_macos(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_macos(monkeypatch)
    result = runner.invoke(app, ["logs", "grep", "fooErr", "--since", "30m", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    args = doc["data"]["args"]
    assert args[0] == "log"
    assert "--last" in args and "30m" in args
    # Predicate body should contain "fooErr" as the CONTAINS arg.
    pred_arg = args[args.index("--predicate") + 1]
    assert "fooErr" in pred_arg
    assert "CONTAINS" in pred_arg


def test_logs_grep_journalctl_form_on_linux(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    result = runner.invoke(
        app,
        [
            "logs",
            "grep",
            "barFail",
            "--since",
            "2 hours ago",
            "--unit",
            "nginx",
            "--json",
        ],
    )
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    args = doc["data"]["args"]
    assert args[0] == "journalctl"
    assert "--since" in args and "2 hours ago" in args
    assert "--grep" in args and "barFail" in args
    assert "-u" in args and "nginx" in args


# ─── system show ────────────────────────────────────────────────────────


def test_logs_system_show_priority_maps_to_nspredicate_on_macos(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_macos(monkeypatch)
    result = runner.invoke(app, ["logs", "system", "show", "--priority", "error", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    args = doc["data"]["args"]
    pred = args[args.index("--predicate") + 1]
    assert 'messageType == "error"' in pred


def test_logs_system_show_priority_maps_to_minus_p_on_linux(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    result = runner.invoke(app, ["logs", "system", "show", "--priority", "err", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    args = doc["data"]["args"]
    assert "-p" in args and "err" in args


def test_logs_system_show_default_lines_applied(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    result = runner.invoke(app, ["logs", "system", "show", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    args = doc["data"]["args"]
    # Default is tools.logs.default_lines = 100.
    assert "-n" in args and "100" in args
