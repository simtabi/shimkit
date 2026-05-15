"""Tests for ``shimkit ports``.

The platform/CommandRunner boundary is mocked via ``Platform.detect``
and ``CommandRunner.run`` monkeypatching. Pure parser logic in
``owners.py`` is tested independently with fixture strings.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult

# ─── pure parsers ────────────────────────────────────────────────────────


def test_parse_lsof_typical_listening_set() -> None:
    from shimkit.tools.ports.owners import parse_lsof

    out = (
        "p1234\n"
        "cnginx\n"
        "unobody\n"
        "f6\n"
        "PTCP\n"
        "n*:80\n"
        "f7\n"
        "PTCP\n"
        "n127.0.0.1:443\n"
        "p5678\n"
        "cnode\n"
        "uimani\n"
        "f18\n"
        "PTCP\n"
        "n127.0.0.1:3000\n"
    )
    owners = parse_lsof(out)
    assert len(owners) == 3
    p80 = next(o for o in owners if o.port == 80)
    assert p80.name == "nginx" and p80.pid == 1234 and p80.user == "nobody"
    assert p80.address is None  # "*" normalised to None
    p443 = next(o for o in owners if o.port == 443)
    assert p443.address == "127.0.0.1"
    p3000 = next(o for o in owners if o.port == 3000)
    assert p3000.name == "node" and p3000.user == "imani"


def test_parse_lsof_ignores_established_connections() -> None:
    from shimkit.tools.ports.owners import parse_lsof

    # Established sockets have "->" in the name field; we only want
    # listeners.
    out = "p1234\nccurl\nuimani\nf5\nPTCP\nn127.0.0.1:54321->93.184.216.34:443\n"
    owners = parse_lsof(out)
    assert owners == []


def test_parse_ss_with_single_owner() -> None:
    from shimkit.tools.ports.owners import parse_ss

    out = (
        "tcp   LISTEN 0  511      0.0.0.0:80   0.0.0.0:*  "
        'users:(("nginx",pid=1234,fd=6))\n'
        "udp   UNCONN 0  0   127.0.0.53%lo:53  0.0.0.0:*  "
        'users:(("systemd-resolve",pid=900,fd=12))\n'
    )
    owners = parse_ss(out)
    assert len(owners) == 2
    assert owners[0].port == 80 and owners[0].proto == "tcp"
    assert owners[0].name == "nginx" and owners[0].pid == 1234
    assert owners[1].port == 53 and owners[1].proto == "udp"
    assert owners[1].address == "127.0.0.53%lo"


def test_parse_ss_with_multiple_owners_per_port() -> None:
    from shimkit.tools.ports.owners import parse_ss

    out = (
        "tcp   LISTEN 0  511   0.0.0.0:80   0.0.0.0:*  "
        'users:(("nginx",pid=1234,fd=6),("nginx",pid=1235,fd=6))\n'
    )
    owners = parse_ss(out)
    assert len(owners) == 2
    assert {o.pid for o in owners} == {1234, 1235}


def test_parse_ss_with_ipv6_brackets() -> None:
    from shimkit.tools.ports.owners import parse_ss

    out = 'tcp   LISTEN 0  511   [::]:443   [::]:*  users:(("nginx",pid=1234,fd=6))\n'
    owners = parse_ss(out)
    assert len(owners) == 1
    assert owners[0].port == 443 and owners[0].address == "::"


def test_parse_ss_handles_empty_users_block() -> None:
    from shimkit.tools.ports.owners import parse_ss

    out = "tcp   LISTEN 0  511   0.0.0.0:5432  0.0.0.0:*  users:()\n"
    owners = parse_ss(out)
    # Still surfaces the port, with pid=0 / name=? as the sentinel.
    assert len(owners) == 1 and owners[0].port == 5432
    assert owners[0].pid == 0 and owners[0].name == "?"


def test_filter_port() -> None:
    from shimkit.tools.ports.models import PortOwner
    from shimkit.tools.ports.owners import filter_port

    rows = [
        PortOwner(port=80, proto="tcp", pid=1, name="a"),
        PortOwner(port=443, proto="tcp", pid=2, name="b"),
        PortOwner(port=80, proto="tcp", pid=3, name="c"),
    ]
    assert {o.pid for o in filter_port(rows, 80)} == {1, 3}
    assert filter_port(rows, 9999) == []


# ─── manager: platform gating ────────────────────────────────────────────


def _force_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Darwin", machine="arm64")),
    )
    monkeypatch.setattr("shimkit.tools.ports.manager.shutil.which", lambda _: "/usr/sbin/lsof")


def _force_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.tools.ports.manager.shutil.which", lambda _: "/usr/bin/ss")


def test_boot_exits_69_on_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.ports.manager import PortsManager

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Windows", machine="x86_64")),
    )
    with pytest.raises(SystemExit) as exc:
        PortsManager.create().boot()
    assert exc.value.code == 69


def test_boot_exits_69_when_lsof_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.ports.manager import PortsManager

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Darwin", machine="arm64")),
    )
    monkeypatch.setattr("shimkit.tools.ports.manager.shutil.which", lambda _: None)
    with pytest.raises(SystemExit) as exc:
        PortsManager.create().boot()
    assert exc.value.code == 69


# ─── CLI: show ───────────────────────────────────────────────────────────


def test_ports_show_json_on_macos(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_macos(monkeypatch)
    lsof_out = "p1234\ncnginx\nunobody\nf6\nPTCP\nn*:80\n"
    monkeypatch.setattr(
        "shimkit.tools.ports.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, lsof_out, "")),
    )
    result = runner.invoke(app, ["ports", "show", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["status"] == "ok"
    assert len(doc["data"]["owners"]) == 1
    assert doc["data"]["owners"][0]["port"] == 80
    assert doc["data"]["owners"][0]["name"] == "nginx"


def test_ports_show_narrows_to_one_port_on_linux(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    ss_out = (
        "tcp   LISTEN 0  511   0.0.0.0:80   0.0.0.0:*  "
        'users:(("nginx",pid=1234,fd=6))\n'
        "tcp   LISTEN 0  511   0.0.0.0:443  0.0.0.0:*  "
        'users:(("nginx",pid=1234,fd=7))\n'
    )
    monkeypatch.setattr(
        "shimkit.tools.ports.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, ss_out, "")),
    )
    result = runner.invoke(app, ["ports", "show", "443", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert len(doc["data"]["owners"]) == 1
    assert doc["data"]["owners"][0]["port"] == 443


def test_ports_show_empty_set(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.ports.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, "", "")),
    )
    result = runner.invoke(app, ["ports", "show"])
    assert result.exit_code == 0


# ─── CLI: kill ───────────────────────────────────────────────────────────


def test_ports_kill_refuses_without_yes_under_no_input(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    ss_out = 'tcp   LISTEN 0  511   0.0.0.0:5000   0.0.0.0:*  users:(("uvicorn",pid=4242,fd=6))\n'
    monkeypatch.setattr(
        "shimkit.tools.ports.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, ss_out, "")),
    )
    result = runner.invoke(app, ["ports", "--no-input", "kill", "5000"])
    assert result.exit_code == 1
    assert "Cancelled" in result.stdout or "Pass --yes" in result.stdout


def test_ports_kill_dry_run_lists_targets_without_signalling(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    ss_out = 'tcp   LISTEN 0  511   0.0.0.0:5000   0.0.0.0:*  users:(("uvicorn",pid=4242,fd=6))\n'
    calls: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        return CommandResult(0, ss_out, "")

    monkeypatch.setattr("shimkit.tools.ports.manager.CommandRunner.run", staticmethod(fake_run))
    result = runner.invoke(app, ["ports", "kill", "5000", "--dry-run", "--yes"])
    assert result.exit_code == 0
    # dry-run shells out for the listing only — no kill(1) invocation.
    assert not any(c and c[0] == "kill" for c in calls)


def test_ports_kill_sends_signal_on_confirmed_run(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    ss_out = 'tcp   LISTEN 0  511   0.0.0.0:5000   0.0.0.0:*  users:(("uvicorn",pid=4242,fd=6))\n'
    kills: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        if cmd and cmd[0] == "kill":
            kills.append(list(cmd))
            return CommandResult(0, "", "")
        return CommandResult(0, ss_out, "")

    monkeypatch.setattr("shimkit.tools.ports.manager.CommandRunner.run", staticmethod(fake_run))
    result = runner.invoke(app, ["ports", "kill", "5000", "--yes"])
    assert result.exit_code == 0
    assert kills == [["kill", "-TERM", "4242"]]


def test_ports_kill_empty_port_is_noop(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.ports.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, "", "")),
    )
    result = runner.invoke(app, ["ports", "kill", "9999", "--yes"])
    assert result.exit_code == 0


def test_ports_kill_refuses_system_tier_without_severe_token(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    # pid 12 is below the default 100 threshold — system tier.
    ss_out = (
        "tcp   LISTEN 0  511   127.0.0.1:11   0.0.0.0:*  "
        'users:(("systemd-something",pid=12,fd=6))\n'
    )
    monkeypatch.setattr(
        "shimkit.tools.ports.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, ss_out, "")),
    )
    result = runner.invoke(app, ["ports", "kill", "11", "--yes"])
    assert result.exit_code == 1
    assert "system-tier" in result.stdout


def test_ports_kill_with_severe_token_proceeds_through_prompt(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    ss_out = (
        "tcp   LISTEN 0  511   127.0.0.1:11   0.0.0.0:*  "
        'users:(("systemd-something",pid=12,fd=6))\n'
    )

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        if cmd and cmd[0] == "kill":
            return CommandResult(0, "", "")
        return CommandResult(0, ss_out, "")

    monkeypatch.setattr("shimkit.tools.ports.manager.CommandRunner.run", staticmethod(fake_run))
    result = runner.invoke(
        app,
        ["ports", "kill", "11", "--yes", "--confirm", "KILL-INIT"],
    )
    assert result.exit_code == 0


def test_ports_kill_rejects_disallowed_signal(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    ss_out = 'tcp   LISTEN 0  511   0.0.0.0:5000   0.0.0.0:*  users:(("uvicorn",pid=4242,fd=6))\n'
    monkeypatch.setattr(
        "shimkit.tools.ports.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, ss_out, "")),
    )
    result = runner.invoke(app, ["ports", "kill", "5000", "--yes", "--signal", "USR1"])
    assert result.exit_code == 1
    assert "Refusing signal" in result.stdout
