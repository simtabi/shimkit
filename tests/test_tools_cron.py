"""Tests for ``shimkit cron``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult
from shimkit.core.platform import Platform
from shimkit.tools.cron import parser
from shimkit.tools.cron.manager import CronManager

# ─── pure parser ────────────────────────────────────────────────────────


def test_is_valid_schedule_at_shorthand() -> None:
    for s in ("@reboot", "@yearly", "@annually", "@monthly", "@weekly", "@daily", "@hourly"):
        assert parser.is_valid_schedule(s)


def test_is_valid_schedule_five_field() -> None:
    assert parser.is_valid_schedule("0 3 * * *")
    assert parser.is_valid_schedule("*/15 * * * *")
    assert parser.is_valid_schedule("0,15,30,45 9-17 * * MON-FRI")


def test_is_valid_schedule_rejects_garbage() -> None:
    assert not parser.is_valid_schedule("")
    assert not parser.is_valid_schedule("nope")
    assert not parser.is_valid_schedule("0 0 0 0")  # only 4 fields
    assert not parser.is_valid_schedule("@nonsense")


def test_is_valid_name() -> None:
    assert parser.is_valid_name("backup")
    assert parser.is_valid_name("daily_backup")
    assert parser.is_valid_name("a")
    assert not parser.is_valid_name("")
    assert not parser.is_valid_name("Backup")  # uppercase
    assert not parser.is_valid_name("1backup")  # starts with digit
    assert not parser.is_valid_name("a" * 65)


def test_parse_roundtrip_preserves_user_content() -> None:
    text = "# user-authored noise\n\nMAILTO=ops@example.com\n0 4 * * * /opt/legacy/cleanup.sh\n"
    items, entries = parser.parse(text, managed_prefix="# shimkit:")
    assert entries == []
    rendered = parser.render(items, managed_prefix="# shimkit:")
    assert rendered == text


def test_parse_recognises_managed_entry() -> None:
    text = "# shimkit:backup nightly DB dump\n0 3 * * * /usr/local/bin/dump.sh\n"
    _items, entries = parser.parse(text, managed_prefix="# shimkit:")
    assert len(entries) == 1
    e = entries[0]
    assert e.name == "backup"
    assert e.schedule == "0 3 * * *"
    assert e.command == "/usr/local/bin/dump.sh"
    assert e.comment == "nightly DB dump"


def test_parse_recognises_at_shorthand_entry() -> None:
    text = "# shimkit:rotate\n@hourly /opt/log/rotate.sh\n"
    _items, entries = parser.parse(text, managed_prefix="# shimkit:")
    assert entries[0].schedule == "@hourly"
    assert entries[0].command == "/opt/log/rotate.sh"


def test_parse_preserves_invalid_managed_marker_as_raw() -> None:
    # Marker followed by something that's not a valid schedule line —
    # we don't try to repair, but we don't drop content either.
    text = "# shimkit:broken\n/something/missing/schedule\n"
    items, entries = parser.parse(text, managed_prefix="# shimkit:")
    assert entries == []
    rendered = parser.render(items, managed_prefix="# shimkit:")
    # Marker line is preserved; the bogus second line is a raw item too.
    assert "# shimkit:broken" in rendered
    assert "/something/missing/schedule" in rendered


def test_render_outputs_both_marker_and_command() -> None:
    from shimkit.tools.cron.models import CronEntry

    entry = CronEntry(name="x", schedule="@daily", command="/bin/true", comment=None)
    out = parser.render([entry], managed_prefix="# shimkit:")
    assert out == "# shimkit:x\n@daily /bin/true\n"


# ─── helpers for CLI tests ──────────────────────────────────────────────


def _force_unix(monkeypatch: pytest.MonkeyPatch, system: str = "Linux") -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system=system, machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.tools.cron.manager.shutil.which", lambda _: "/usr/bin/crontab")


def _stub_crontab_runner(
    monkeypatch: pytest.MonkeyPatch, *, initial_body: str = ""
) -> dict[str, str | list[list[str]]]:
    """Stub `crontab -l` to read from `state['body']`; stub
    `crontab <file>` to overwrite `state['body']` with the file
    contents. Returns the shared state dict so tests can inspect.
    """
    state: dict[str, str | list[list[str]]] = {
        "body": initial_body,
        "calls": [],
    }

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        cmd_l = list(cmd)
        state["calls"].append(cmd_l)  # type: ignore[union-attr]
        if cmd_l == ["crontab", "-l"]:
            return CommandResult(0, state["body"], "")  # type: ignore[arg-type]
        if cmd_l[0] == "crontab" and len(cmd_l) == 2:
            # crontab <file> — read the file body, store it.
            try:
                state["body"] = Path(cmd_l[1]).read_text(encoding="utf-8")
            except OSError as exc:
                return CommandResult(1, "", str(exc))
            return CommandResult(0, "", "")
        return CommandResult(0, "", "")

    monkeypatch.setattr("shimkit.tools.cron.manager.CommandRunner.run", staticmethod(fake_run))
    return state


# ─── platform / binary gating ───────────────────────────────────────────


def test_boot_exits_69_on_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Windows", machine="x86_64")),
    )
    with pytest.raises(SystemExit) as exc:
        CronManager.create().boot()
    assert exc.value.code == 69


def test_boot_exits_69_when_crontab_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.tools.cron.manager.shutil.which", lambda _: None)
    with pytest.raises(SystemExit) as exc:
        CronManager.create().boot()
    assert exc.value.code == 69


# ─── show + list ────────────────────────────────────────────────────────


def test_show_empty_crontab(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_unix(monkeypatch)
    _stub_crontab_runner(monkeypatch, initial_body="")
    result = runner.invoke(app, ["cron", "show", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["body"] == ""


def test_list_empty_when_no_managed_entries(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch)
    _stub_crontab_runner(monkeypatch, initial_body="0 4 * * * /opt/legacy/cleanup.sh\n")
    result = runner.invoke(app, ["cron", "list", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["entries"] == []


def test_list_reports_managed_entries(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_unix(monkeypatch)
    initial = (
        "# shimkit:backup nightly\n"
        "0 3 * * * /usr/local/bin/dump.sh\n"
        "# shimkit:rotate\n"
        "@hourly /opt/log/rotate.sh\n"
    )
    _stub_crontab_runner(monkeypatch, initial_body=initial)
    result = runner.invoke(app, ["cron", "list", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    names = {e["name"] for e in doc["data"]["entries"]}
    assert names == {"backup", "rotate"}


# ─── add ────────────────────────────────────────────────────────────────


def test_add_writes_marker_and_schedule_lines(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _force_unix(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    state = _stub_crontab_runner(monkeypatch)
    result = runner.invoke(
        app,
        [
            "cron",
            "add",
            "--yes",
            "--name",
            "backup",
            "--schedule",
            "0 3 * * *",
            "--cmd",
            "/usr/local/bin/dump.sh",
        ],
    )
    assert result.exit_code == 0
    body = state["body"]
    assert "# shimkit:backup" in body
    assert "0 3 * * * /usr/local/bin/dump.sh" in body


def test_add_with_comment_renders_inline(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _force_unix(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    state = _stub_crontab_runner(monkeypatch)
    result = runner.invoke(
        app,
        [
            "cron",
            "add",
            "--yes",
            "--name",
            "backup",
            "--schedule",
            "@daily",
            "--cmd",
            "/bin/true",
            "--comment",
            "nightly fast check",
        ],
    )
    assert result.exit_code == 0
    assert "# shimkit:backup nightly fast check" in state["body"]


def test_add_refuses_invalid_name(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_unix(monkeypatch)
    _stub_crontab_runner(monkeypatch)
    result = runner.invoke(
        app,
        [
            "cron",
            "add",
            "--yes",
            "--name",
            "Bad-Name",  # uppercase
            "--schedule",
            "@daily",
            "--cmd",
            "/bin/true",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid name" in result.stdout


def test_add_refuses_invalid_schedule(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_unix(monkeypatch)
    _stub_crontab_runner(monkeypatch)
    result = runner.invoke(
        app,
        [
            "cron",
            "add",
            "--yes",
            "--name",
            "x",
            "--schedule",
            "not-a-cron-expression",
            "--cmd",
            "/bin/true",
        ],
    )
    assert result.exit_code == 1
    assert "Invalid schedule" in result.stdout


def test_add_refuses_duplicate_name(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _force_unix(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    initial = "# shimkit:backup\n@daily /usr/bin/true\n"
    _stub_crontab_runner(monkeypatch, initial_body=initial)
    result = runner.invoke(
        app,
        [
            "cron",
            "add",
            "--yes",
            "--name",
            "backup",
            "--schedule",
            "@hourly",
            "--cmd",
            "/bin/false",
        ],
    )
    assert result.exit_code == 1
    assert "already exists" in result.stdout


def test_add_refuses_under_no_input(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_unix(monkeypatch)
    _stub_crontab_runner(monkeypatch)
    result = runner.invoke(
        app,
        [
            "cron",
            "--no-input",
            "add",
            "--name",
            "x",
            "--schedule",
            "@daily",
            "--cmd",
            "/bin/true",
        ],
    )
    assert result.exit_code == 1


def test_add_dry_run_makes_no_changes(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _force_unix(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    state = _stub_crontab_runner(monkeypatch)
    result = runner.invoke(
        app,
        [
            "cron",
            "add",
            "--yes",
            "--dry-run",
            "--name",
            "x",
            "--schedule",
            "@daily",
            "--cmd",
            "/bin/true",
        ],
    )
    assert result.exit_code == 0
    assert state["body"] == ""  # no write happened


# ─── remove ─────────────────────────────────────────────────────────────


def test_remove_drops_marker_and_schedule_lines(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _force_unix(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    initial = (
        "# user comment, unrelated\n"
        "# shimkit:backup\n"
        "0 3 * * * /usr/local/bin/dump.sh\n"
        "# shimkit:rotate\n"
        "@hourly /opt/log/rotate.sh\n"
    )
    state = _stub_crontab_runner(monkeypatch, initial_body=initial)
    result = runner.invoke(app, ["cron", "remove", "backup", "--yes"])
    assert result.exit_code == 0
    body = state["body"]
    assert "# shimkit:backup" not in body
    assert "/usr/local/bin/dump.sh" not in body
    # The other managed entry is left untouched.
    assert "# shimkit:rotate" in body
    # The user comment is preserved.
    assert "# user comment, unrelated" in body


def test_remove_missing_entry_is_noop(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_unix(monkeypatch)
    _stub_crontab_runner(monkeypatch)
    result = runner.invoke(app, ["cron", "remove", "absent", "--yes"])
    assert result.exit_code == 0
    assert "nothing to remove" in result.stdout


# ─── rollback ───────────────────────────────────────────────────────────


def test_rollback_restores_most_recent_backup(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _force_unix(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    state = _stub_crontab_runner(monkeypatch, initial_body="current body\n")
    # Drop a backup.
    backup_dir = tmp_path / ".shimkit" / "data" / "cron"
    backup_dir.mkdir(parents=True)
    (backup_dir / "crontab-20260101000000.bak").write_text("older\n")
    (backup_dir / "crontab-20260201000000.bak").write_text("restored body\n")
    result = runner.invoke(app, ["cron", "rollback", "--yes"])
    assert result.exit_code == 0
    assert state["body"] == "restored body\n"


def test_rollback_with_no_backups_errors(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _force_unix(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    _stub_crontab_runner(monkeypatch)
    result = runner.invoke(app, ["cron", "rollback", "--yes"])
    assert result.exit_code == 1
