"""Final coverage push for v0.10.0.

Targets specific methods across multiple managers: adguard service /
logs / rollback / config_validate, java commands, shell upgrader,
tls cron-install + status, db status edges, ports manager, web
nginx vhost edges, dns fixer thin spots.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── adguard manager ──────────────────────────────────────────────────


def _build_adguard_manager(monkeypatch: pytest.MonkeyPatch, with_install: bool = True):
    """Build an AdGuardManager with mocked install + systemd."""
    from shimkit.tools.adguard import manager as _amgr
    from shimkit.tools.adguard.models import AdGuardInstall

    mgr = _amgr.AdGuardManager()
    if with_install:
        mgr._install = AdGuardInstall(
            binary=Path("/opt/AdGuardHome/AdGuardHome"),
            yaml_path=Path("/opt/AdGuardHome/AdGuardHome.yaml"),
            install_root=Path("/opt/AdGuardHome"),
        )
    return mgr


def test_adguard_service_status_active(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core import systemd as _sd

    monkeypatch.setattr(
        _sd.Systemd,
        "state",
        staticmethod(
            lambda unit: _sd.UnitState(name=unit, active=True, enabled=True, exists=True)
        ),
    )
    mgr = _build_adguard_manager(monkeypatch)
    assert mgr.service("status") == 0


def test_adguard_service_status_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core import systemd as _sd

    monkeypatch.setattr(
        _sd.Systemd,
        "state",
        staticmethod(
            lambda unit: _sd.UnitState(name=unit, active=False, enabled=False, exists=True)
        ),
    )
    mgr = _build_adguard_manager(monkeypatch)
    assert mgr.service("status") == 1


def test_adguard_service_unknown_action(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _build_adguard_manager(monkeypatch)
    assert mgr.service("teleport") == 1


def test_adguard_service_start_calls_systemd(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core import systemd as _sd

    calls: list[str] = []

    def fake_start(unit):  # type: ignore[no-untyped-def]
        calls.append(unit)
        return CommandResult(0, "", "")

    monkeypatch.setattr(_sd.Systemd, "start", staticmethod(fake_start))
    mgr = _build_adguard_manager(monkeypatch)
    assert mgr.service("start") == 0
    assert calls == ["AdGuardHome"]


def test_adguard_logs_invokes_journal(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core import systemd as _sd

    calls: list[tuple[str, int, bool]] = []

    def fake_journal(unit, lines=80, follow=False):  # type: ignore[no-untyped-def]
        calls.append((unit, lines, follow))
        return CommandResult(0, "", "")

    monkeypatch.setattr(_sd.Systemd, "journal", staticmethod(fake_journal))
    mgr = _build_adguard_manager(monkeypatch)
    assert mgr.logs(lines=100, follow=True) == 0
    assert calls == [("AdGuardHome", 100, True)]


def test_adguard_rollback_no_backups(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.adguard import resolv as _resolv
    from shimkit.tools.adguard.models import AdGuardInstall

    monkeypatch.setattr(_resolv, "latest_resolv_backup", lambda: None)
    mgr = _build_adguard_manager(monkeypatch, with_install=False)
    mgr._install = AdGuardInstall(
        binary=tmp_path / "AdGuardHome",
        yaml_path=tmp_path / "missing.yaml",
        install_root=tmp_path,
    )
    assert mgr.rollback() == 1


def test_adguard_rollback_restores_yaml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.adguard import resolv as _resolv
    from shimkit.tools.adguard.models import AdGuardInstall

    monkeypatch.setattr(_resolv, "latest_resolv_backup", lambda: None)
    yaml_dir = tmp_path / "agh"
    yaml_dir.mkdir()
    yaml = yaml_dir / "AdGuardHome.yaml"
    yaml.write_text("current")
    bak = yaml_dir / "AdGuardHome.yaml.bak-20260515"
    bak.write_text("backup content")
    mgr = _build_adguard_manager(monkeypatch, with_install=False)
    mgr._install = AdGuardInstall(
        binary=yaml_dir / "AdGuardHome",
        yaml_path=yaml,
        install_root=yaml_dir,
    )
    assert mgr.rollback() == 0
    assert yaml.read_text() == "backup content"


# ─── tls manager edges ────────────────────────────────────────────────


def test_tls_revoke_dry_run_does_not_run_certbot(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cover the dry-run branch of revoke."""
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )

    class _FakeEnv:
        @classmethod
        def create(cls):  # type: ignore[no-untyped-def]
            return cls()

        def boot(self):
            return self

        def run_oneshot(self, *a, **kw):  # type: ignore[no-untyped-def]
            raise AssertionError("dry-run should not invoke run_oneshot")

    monkeypatch.setattr("shimkit.tools.tls.manager.DockerEnv", _FakeEnv)
    monkeypatch.setattr("shimkit.tools.tls.manager._vc.preflight", lambda *a, **kw: None)
    monkeypatch.setenv("HOME", str(tmp_path))
    from shimkit.config import reset_cache

    reset_cache()
    # Seed a live cert dir.
    live = (
        tmp_path
        / ".shimkit"
        / "data"
        / "tls"
        / "etc-letsencrypt"
        / "live"
        / "example.com"
    )
    live.mkdir(parents=True)
    (live / "fullchain.pem").write_text("fake")
    result = runner.invoke(
        app,
        [
            "tls",
            "revoke",
            "-d",
            "example.com",
            "--confirm",
            "REVOKE-TLS",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "would run" in result.output.lower()


def test_tls_revoke_missing_domain_arg(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Typer requires --domain. Without it: usage error."""
    result = runner.invoke(app, ["tls", "revoke", "--confirm", "REVOKE-TLS"])
    # Typer exits 2 on missing required option.
    assert result.exit_code == 2


# ─── db manager status / ls edges ─────────────────────────────────────


def test_db_status_when_container_missing(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """status reports `missing` for a container that doesn't exist."""
    from unittest.mock import MagicMock

    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.core.version.preflight", lambda *a, **kw: None)

    import types

    fake = types.ModuleType("docker.errors")

    class _NotFound(Exception):  # noqa: N818
        pass

    fake.NotFound = _NotFound  # type: ignore[attr-defined]
    import sys as _sys

    monkeypatch.setitem(_sys.modules, "docker.errors", fake)
    client = MagicMock()
    client.containers.get.side_effect = _NotFound
    monkeypatch.setattr("shimkit.core.docker._from_env", lambda: client)
    result = runner.invoke(app, ["db", "mysql", "status", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.output)
    assert doc["data"]["state"] == "missing"


# ─── docker_clean status / schedule emit ──────────────────────────────


def test_docker_clean_schedule_emits_snippet(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`docker-clean schedule` doesn't need a daemon — pure stdout.
    On macOS it emits a launchd plist; on Linux, a systemd timer.
    The combined output mentions either shimkit or docker-clean."""
    monkeypatch.setattr("shimkit.core.version.preflight", lambda *a, **kw: None)
    result = runner.invoke(app, ["docker-clean", "schedule"])
    assert result.exit_code == 0
    assert "shimkit" in result.output


# ─── shell manager menu paths ─────────────────────────────────────────


def test_shell_manager_menu_upgrade_picks_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.shell import manager as _shellmgr

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )

    class FakePM:
        name = "apt"

    monkeypatch.setattr(
        _shellmgr.PackageManager, "detect", classmethod(lambda cls, _: FakePM())
    )
    m = _shellmgr.ShellManager.create().boot()
    upgrader = MagicMock()
    upgrader.supported_shells = ["bash"]
    m._upgrader = upgrader  # type: ignore[assignment]
    # User picks "Back".
    monkeypatch.setattr(
        "shimkit.tools.shell.manager.Menu.select", lambda *a, **kw: "← Back"
    )
    m._menu_upgrade()  # exits early, no upgrade call
    upgrader.upgrade.assert_not_called()


def test_shell_manager_menu_simulate_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.shell import manager as _shellmgr

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )

    class FakePM:
        name = "apt"

    monkeypatch.setattr(
        _shellmgr.PackageManager, "detect", classmethod(lambda cls, _: FakePM())
    )
    m = _shellmgr.ShellManager.create().boot()
    upgrader = MagicMock()
    upgrader.supported_shells = ["bash"]
    m._upgrader = upgrader  # type: ignore[assignment]
    monkeypatch.setattr(
        "shimkit.tools.shell.manager.Menu.select", lambda *a, **kw: "← Back"
    )
    m._menu_simulate()
    upgrader.simulate.assert_not_called()


def test_shell_manager_menu_run_exits_on_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.shell import manager as _shellmgr

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )

    class FakePM:
        name = "apt"

    monkeypatch.setattr(
        _shellmgr.PackageManager, "detect", classmethod(lambda cls, _: FakePM())
    )
    m = _shellmgr.ShellManager.create().boot()
    upgrader = MagicMock()
    upgrader.supported_shells = ["bash"]
    m._upgrader = upgrader  # type: ignore[assignment]
    monkeypatch.setattr(
        "shimkit.tools.shell.manager.Menu.select", lambda *a, **kw: None
    )
    m.run()  # None choice exits the loop cleanly


# ─── ssh manager — perms_fix dry-run + perms_audit json ──────────────


def test_ssh_perms_audit_json_clean(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir(mode=0o700)
    # No keys = no issues.
    result = runner.invoke(app, ["ssh", "perms", "audit", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.output)
    assert doc["data"]["issues"] == []


# ─── env manager scaffold ─────────────────────────────────────────────


def test_env_scaffold_writes_template(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / ".env"
    result = runner.invoke(app, ["env", "scaffold", str(target)])
    assert result.exit_code == 0
    body = target.read_text()
    # Default template includes some recognisable keys.
    assert "=" in body
    assert target.is_file()


def test_env_scaffold_refuses_overwrite(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / ".env"
    target.write_text("existing\n")
    result = runner.invoke(app, ["env", "scaffold", str(target)])
    assert result.exit_code != 0


def test_env_diff_two_files(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    a = tmp_path / "a.env"
    b = tmp_path / "b.env"
    a.write_text("SHARED=1\nONLY_A=2\n", encoding="utf-8")
    b.write_text("SHARED=1\nONLY_B=3\n", encoding="utf-8")
    result = runner.invoke(app, ["env", "diff", str(a), str(b), "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.output)
    only_in_a = set(doc["data"]["only_a"])
    only_in_b = set(doc["data"]["only_b"])
    assert "ONLY_A" in only_in_a
    assert "ONLY_B" in only_in_b


# ─── hosts manager add / remove / block / unblock ─────────────────────


def test_hosts_add_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"
    hp.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    mgr = HostsManager()
    mgr._hosts_path = hp
    assert mgr.add("10.0.0.1", "myhost", dry_run=True) == 0


def test_hosts_add_invalid_ip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"
    hp.write_text("", encoding="utf-8")
    mgr = HostsManager()
    mgr._hosts_path = hp
    assert mgr.add("not-an-ip", "host", dry_run=True) == 1


def test_hosts_remove_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"
    hp.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    mgr = HostsManager()
    mgr._hosts_path = hp
    assert mgr.remove("absent.example.com") == 0


def test_hosts_block_and_unblock_delegate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"
    hp.write_text("127.0.0.1 localhost\n", encoding="utf-8")

    def fake_install(self, src, dst):  # type: ignore[no-untyped-def]
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return True

    monkeypatch.setattr(HostsManager, "_sudo_install", fake_install)
    mgr = HostsManager()
    mgr._hosts_path = hp

    class _Cfg:
        max_entries_per_apply = 1000

    monkeypatch.setattr(
        "shimkit.tools.hosts.manager.get_config",
        lambda: type(
            "Cfg", (), {"tools": type("Tools", (), {"hosts": _Cfg()})()}
        )(),
    )
    assert mgr.block("ads.test") == 0
    assert "ads.test" in hp.read_text()
    assert mgr.unblock("ads.test") == 0
    assert "ads.test" not in hp.read_text()
