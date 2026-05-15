"""Tests for ``shimkit hosts``.

Atomic-write semantics are exercised via a tmp_path hosts file +
``--path`` override on every mutator. CommandRunner is monkeypatched
so the ``sudo install`` step short-circuits to a Python copy.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult

# ─── pure editor ────────────────────────────────────────────────────────


def test_editor_parses_and_renders_roundtrip() -> None:
    from shimkit.tools.hosts.editor import HostsFile

    text = (
        "# header\n"
        "127.0.0.1\tlocalhost\n"
        "::1\tlocalhost ip6-localhost\n"
        "\n"
        "192.168.1.10\tnas.local\t# my NAS\n"
    )
    hf = HostsFile.parse(text)
    rendered = hf.render()
    # round-trip preserves the header + blank, idiomatic spacing for
    # multi-name lines.
    assert "# header" in rendered
    assert "127.0.0.1\tlocalhost" in rendered
    assert "::1\tlocalhost ip6-localhost" in rendered
    assert "nas.local" in rendered and "# my NAS" in rendered


def test_editor_add_is_idempotent() -> None:
    from shimkit.tools.hosts.editor import HostsFile

    hf = HostsFile.parse("127.0.0.1\tlocalhost\n")
    assert hf.add("10.0.0.1", "kube.local") is True
    assert hf.add("10.0.0.1", "kube.local") is False
    assert len(hf.find("kube.local")) == 1


def test_editor_remove_returns_count() -> None:
    from shimkit.tools.hosts.editor import HostsFile

    hf = HostsFile.parse("10.0.0.1\thost.local\n10.0.0.2\thost.local\n10.0.0.3\tother\n")
    assert hf.remove("host.local") == 2
    assert hf.has("host.local") is False
    assert hf.has("other") is True


def test_is_valid_ip() -> None:
    from shimkit.tools.hosts.editor import is_valid_ip

    assert is_valid_ip("127.0.0.1")
    assert is_valid_ip("255.255.255.255")
    assert is_valid_ip("::1")
    assert is_valid_ip("2001:db8::1")
    assert not is_valid_ip("256.0.0.1")
    assert not is_valid_ip("not-an-ip")
    assert not is_valid_ip("")


def test_parse_block_list_handles_stevenblack_format() -> None:
    from shimkit.tools.hosts.editor import parse_block_list

    text = (
        "# A list\n"
        "0.0.0.0 ads.example.com\n"
        "0.0.0.0 trackers.example.com  # inline\n"
        "  \n"
        "bad-line-no-ip\n"
        "0.0.0.0 ads.example.com\n"  # duplicate
    )
    pairs = parse_block_list(text)
    assert pairs == [
        ("0.0.0.0", "ads.example.com"),
        ("0.0.0.0", "trackers.example.com"),
    ]


# ─── helpers ────────────────────────────────────────────────────────────


@pytest.fixture
def hosts_file(tmp_path: Path) -> Path:
    p = tmp_path / "hosts"
    p.write_text(
        "127.0.0.1\tlocalhost\n::1\tlocalhost ip6-localhost\n192.168.1.10\tnas.local\n",
        encoding="utf-8",
    )
    return p


def _stub_sudo_install(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Pretend `sudo install ...` worked by doing a plain file copy.

    Returns the list of every command attempted via CommandRunner so
    tests can assert against it.
    """
    captured: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        cmd_l = list(cmd)
        captured.append(cmd_l)
        # Resolve "install -m … <src> <dst>" by copying src → dst.
        if "install" in cmd_l:
            src = cmd_l[-2]
            dst = cmd_l[-1]
            shutil.copy(src, dst)
            return CommandResult(0, "", "")
        if "cp" in cmd_l:
            src = cmd_l[-2]
            dst = cmd_l[-1]
            shutil.copy(src, dst)
            return CommandResult(0, "", "")
        return CommandResult(0, "", "")

    monkeypatch.setattr("shimkit.tools.hosts.manager.CommandRunner.run", staticmethod(fake_run))
    # No sudo prefix on test runner.
    monkeypatch.setattr("shimkit.tools.hosts.manager.sudo_prefix", lambda: [])
    return captured


# ─── platform gating ────────────────────────────────────────────────────


def test_boot_exits_69_on_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch, hosts_file: Path
) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.hosts.manager import HostsManager

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Windows", machine="x86_64")),
    )
    with pytest.raises(SystemExit) as exc:
        HostsManager.create().boot(hosts_path_override=hosts_file)
    assert exc.value.code == 69


def test_boot_exits_69_on_missing_hosts_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.hosts.manager import HostsManager

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    with pytest.raises(SystemExit) as exc:
        HostsManager.create().boot(hosts_path_override=tmp_path / "missing")
    assert exc.value.code == 69


def _force_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )


# ─── show ───────────────────────────────────────────────────────────────


def test_hosts_show_json(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, hosts_file: Path
) -> None:
    _force_linux(monkeypatch)
    result = runner.invoke(app, ["hosts", "show", "--path", str(hosts_file), "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["status"] == "ok"
    names = {e["name"] for e in doc["data"]["entries"]}
    assert "localhost" in names and "nas.local" in names


# ─── add / remove ───────────────────────────────────────────────────────


def test_hosts_add_writes_atomically(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, hosts_file: Path
) -> None:
    _force_linux(monkeypatch)
    _stub_sudo_install(monkeypatch)
    result = runner.invoke(
        app,
        [
            "hosts",
            "add",
            "10.20.30.40",
            "myapp.local",
            "--path",
            str(hosts_file),
            "--yes",
        ],
    )
    assert result.exit_code == 0
    body = hosts_file.read_text()
    assert "10.20.30.40" in body and "myapp.local" in body


def test_hosts_add_refuses_invalid_ip(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, hosts_file: Path
) -> None:
    _force_linux(monkeypatch)
    _stub_sudo_install(monkeypatch)
    result = runner.invoke(
        app,
        [
            "hosts",
            "add",
            "not-an-ip",
            "myapp.local",
            "--path",
            str(hosts_file),
            "--yes",
        ],
    )
    assert result.exit_code == 1
    assert "Not a valid IP" in result.stdout


def test_hosts_add_idempotent_noop_on_duplicate(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, hosts_file: Path
) -> None:
    _force_linux(monkeypatch)
    _stub_sudo_install(monkeypatch)
    result = runner.invoke(
        app,
        ["hosts", "add", "127.0.0.1", "localhost", "--path", str(hosts_file), "--yes"],
    )
    assert result.exit_code == 0
    assert "already present" in result.stdout


def test_hosts_remove(runner: CliRunner, monkeypatch: pytest.MonkeyPatch, hosts_file: Path) -> None:
    _force_linux(monkeypatch)
    _stub_sudo_install(monkeypatch)
    result = runner.invoke(
        app,
        ["hosts", "remove", "nas.local", "--path", str(hosts_file), "--yes"],
    )
    assert result.exit_code == 0
    assert "nas.local" not in hosts_file.read_text()


# ─── block / unblock ────────────────────────────────────────────────────


def test_hosts_block_adds_127_entry(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, hosts_file: Path
) -> None:
    _force_linux(monkeypatch)
    _stub_sudo_install(monkeypatch)
    result = runner.invoke(
        app,
        ["hosts", "block", "ads.example.com", "--path", str(hosts_file), "--yes"],
    )
    assert result.exit_code == 0
    body = hosts_file.read_text()
    assert "127.0.0.1\tads.example.com" in body or "127.0.0.1 ads.example.com" in body


def test_hosts_unblock_removes_entry(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, hosts_file: Path
) -> None:
    _force_linux(monkeypatch)
    _stub_sudo_install(monkeypatch)
    hosts_file.write_text(hosts_file.read_text() + "127.0.0.1\tads.example.com\n")
    result = runner.invoke(
        app,
        ["hosts", "unblock", "ads.example.com", "--path", str(hosts_file), "--yes"],
    )
    assert result.exit_code == 0
    assert "ads.example.com" not in hosts_file.read_text()


# ─── apply-list ─────────────────────────────────────────────────────────


def test_hosts_apply_list_refuses_without_severe_token(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, hosts_file: Path
) -> None:
    _force_linux(monkeypatch)
    list_file = tmp_path / "list.txt"
    list_file.write_text("0.0.0.0 a.example\n0.0.0.0 b.example\n")
    result = runner.invoke(
        app,
        ["hosts", "apply-list", str(list_file), "--path", str(hosts_file)],
    )
    assert result.exit_code == 1
    assert "severe" in result.stdout.lower() or "APPLY-LIST" in result.stdout


def test_hosts_apply_list_writes_with_severe_token(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, hosts_file: Path
) -> None:
    _force_linux(monkeypatch)
    _stub_sudo_install(monkeypatch)
    list_file = tmp_path / "list.txt"
    list_file.write_text("# header\n0.0.0.0 a.example\n0.0.0.0 b.example\n")
    result = runner.invoke(
        app,
        [
            "hosts",
            "apply-list",
            str(list_file),
            "--path",
            str(hosts_file),
            "--confirm",
            "APPLY-LIST",
        ],
    )
    assert result.exit_code == 0
    body = hosts_file.read_text()
    assert "a.example" in body and "b.example" in body


def test_hosts_apply_list_capped_at_max_entries(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, hosts_file: Path
) -> None:
    _force_linux(monkeypatch)
    _stub_sudo_install(monkeypatch)
    # Synthesise a list bigger than the configured cap (default 5000).
    cfg_override = tmp_path / "shimkit.json"
    cfg_override.write_text('{"tools": {"hosts": {"max_entries_per_apply": 3}}}')
    monkeypatch.setenv("SHIMKIT_CONFIG", str(cfg_override))
    from shimkit.config import reset_cache

    reset_cache()

    list_file = tmp_path / "list.txt"
    list_file.write_text("\n".join(f"0.0.0.0 host{i}.example" for i in range(10)) + "\n")
    result = runner.invoke(
        app,
        [
            "hosts",
            "apply-list",
            str(list_file),
            "--path",
            str(hosts_file),
            "--confirm",
            "APPLY-LIST",
        ],
    )
    assert result.exit_code == 1
    assert "cap" in result.stdout.lower() or "10" in result.stdout


# ─── rollback ───────────────────────────────────────────────────────────


def test_hosts_rollback_restores_latest_backup(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, hosts_file: Path
) -> None:
    _force_linux(monkeypatch)
    _stub_sudo_install(monkeypatch)
    # Lay down a backup that differs from current state.
    bak = hosts_file.with_name(f"{hosts_file.name}.bak-20260514120000")
    bak.write_text("127.0.0.1\told-state\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["hosts", "rollback", "--path", str(hosts_file), "--yes"],
    )
    assert result.exit_code == 0
    assert hosts_file.read_text() == "127.0.0.1\told-state\n"


def test_hosts_rollback_fails_with_no_backup(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, hosts_file: Path
) -> None:
    _force_linux(monkeypatch)
    _stub_sudo_install(monkeypatch)
    result = runner.invoke(
        app,
        ["hosts", "rollback", "--path", str(hosts_file), "--yes"],
    )
    assert result.exit_code == 1
    assert "No backup" in result.stdout


# ─── moderate-prompt refusal ────────────────────────────────────────────


def test_hosts_add_refuses_without_yes_under_no_input(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, hosts_file: Path
) -> None:
    _force_linux(monkeypatch)
    _stub_sudo_install(monkeypatch)
    result = runner.invoke(
        app,
        [
            "hosts",
            "--no-input",
            "add",
            "10.20.30.40",
            "myapp.local",
            "--path",
            str(hosts_file),
        ],
    )
    assert result.exit_code == 1
    assert "Cancelled" in result.stdout or "Pass --yes" in result.stdout
