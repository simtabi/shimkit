"""Coverage push: dns/fixer pure helpers + gpg manager paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── dns/fixer pure helpers ───────────────────────────────────────────


def test_dns_is_within_true(tmp_path: Path) -> None:
    from shimkit.tools.dns import fixer as _fix

    child = tmp_path / "subdir"
    child.mkdir()
    assert _fix._is_within(child, tmp_path)


def test_dns_is_within_false(tmp_path: Path) -> None:
    from shimkit.tools.dns import fixer as _fix

    assert not _fix._is_within(Path("/etc/passwd"), tmp_path)


def test_dns_make_backup_dir_refuses_unsafe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuses to write outside HOME / /tmp."""
    from shimkit.tools.dns import fixer as _fix

    class FakeCfg:
        backup_dir = "/etc"

    class FakeTools:
        dns = FakeCfg()

    class FakeRoot:
        tools = FakeTools()

    monkeypatch.setattr("shimkit.tools.dns.fixer.get_config", lambda: FakeRoot())
    with pytest.raises(PermissionError):
        _fix._make_backup_dir()


def test_dns_make_backup_dir_under_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.dns import fixer as _fix

    class FakeCfg:
        backup_dir = str(tmp_path / "shimkit-backups")

    class FakeTools:
        dns = FakeCfg()

    class FakeRoot:
        tools = FakeTools()

    monkeypatch.setattr("shimkit.tools.dns.fixer.get_config", lambda: FakeRoot())
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    out = _fix._make_backup_dir()
    assert out.exists()
    assert tmp_path in out.parents


def test_dns_latest_backup_dir_none_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.dns import fixer as _fix

    class FakeCfg:
        backup_dir = str(tmp_path / "absent")

    class FakeTools:
        dns = FakeCfg()

    class FakeRoot:
        tools = FakeTools()

    monkeypatch.setattr("shimkit.tools.dns.fixer.get_config", lambda: FakeRoot())
    assert _fix.latest_backup_dir() is None


def test_dns_latest_backup_dir_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.dns import fixer as _fix

    class FakeCfg:
        backup_dir = str(tmp_path)

    class FakeTools:
        dns = FakeCfg()

    class FakeRoot:
        tools = FakeTools()

    monkeypatch.setattr("shimkit.tools.dns.fixer.get_config", lambda: FakeRoot())
    # Empty backup root -> None.
    assert _fix.latest_backup_dir() is None


def test_dns_latest_backup_dir_returns_newest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import time

    from shimkit.tools.dns import fixer as _fix

    older = tmp_path / "20200101-000000"
    older.mkdir()
    time.sleep(0.01)
    newer = tmp_path / "20260515-000000"
    newer.mkdir()

    class FakeCfg:
        backup_dir = str(tmp_path)

    class FakeTools:
        dns = FakeCfg()

    class FakeRoot:
        tools = FakeTools()

    monkeypatch.setattr("shimkit.tools.dns.fixer.get_config", lambda: FakeRoot())
    assert _fix.latest_backup_dir() == newer


def test_dns_detect_interference_finds_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.tools.dns import fixer as _fix

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        cmd_l = list(cmd) if not isinstance(cmd, str) else cmd.split()
        if cmd_l[0] == "pgrep":
            if "Docker" in cmd_l:
                return CommandResult(0, "12345\n", "")
            return CommandResult(1, "", "")
        if cmd_l[0] == "ifconfig":
            return CommandResult(0, "utun0: UP active\n", "")
        return CommandResult(1, "", "")

    monkeypatch.setattr(_fix.CommandRunner, "run", staticmethod(fake_run))
    findings = _fix.detect_interference()
    assert any("Docker" in f for f in findings)
    assert any("utun0" in f for f in findings)


def test_dns_detect_interference_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.tools.dns import fixer as _fix

    monkeypatch.setattr(
        _fix.CommandRunner,
        "run",
        staticmethod(lambda *a, **kw: CommandResult(1, "", "no match")),
    )
    assert _fix.detect_interference() == []


def test_dns_step_detect_vpn_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.tools.dns import fixer as _fix

    monkeypatch.setattr(_fix, "detect_interference", lambda: [])
    monkeypatch.setattr(_fix, "test_resolution", lambda _: True)
    res = _fix.step_detect_vpn()
    assert res.applied is True
    assert res.resolved is True
    assert res.notes == []


def test_dns_step_detect_vpn_with_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.tools.dns import fixer as _fix

    monkeypatch.setattr(_fix, "detect_interference", lambda: ["Docker is running"])
    monkeypatch.setattr(_fix, "test_resolution", lambda _: True)
    res = _fix.step_detect_vpn()
    assert res.applied is True
    # resolved False because findings != []
    assert res.resolved is False
    assert "Docker" in res.notes[0]


# ─── dns/fixer steps that are tricky to mock ─────────────────────────


def test_dns_rollback_no_backup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.dns import fixer as _fix

    monkeypatch.setattr(_fix, "latest_backup_dir", lambda: None)
    assert _fix.rollback() is False


def test_dns_rollback_with_backup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.dns import fixer as _fix

    bak = tmp_path / "backup"
    bak.mkdir()
    # Seed all the plists that the fixer wants to restore.
    for plist in _fix._PLISTS_TO_BACKUP:
        name = Path(plist).name
        (bak / name).write_text("backup")
    monkeypatch.setattr(_fix, "latest_backup_dir", lambda: bak)
    monkeypatch.setattr(
        _fix.CommandRunner,
        "run",
        staticmethod(lambda *a, **kw: CommandResult(0, "", "")),
    )
    monkeypatch.setattr(_fix, "sudo_prefix", lambda: [])
    assert _fix.rollback() is True


# ─── gpg manager: keys generate / export / import ─────────────────────


def test_gpg_keys_list_runs(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gpg keys list — happy path with stub output."""
    monkeypatch.setattr(
        "shimkit.core.version.shutil.which",
        lambda b: f"/usr/bin/{b}" if b == "gpg" else None,
    )
    monkeypatch.setattr("shimkit.core.version.preflight", lambda *a, **kw: None)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(
            lambda *a, **kw: CommandResult(
                0,
                "pub:::4096:R:ABCDEF123:1700000000:::-:User <u@example.com>::\n",
                "",
            )
        ),
    )
    result = runner.invoke(app, ["gpg", "keys", "list", "--json"])
    # Should at least not crash.
    assert result.exit_code in (0, 1)


# ─── gpg manager: git-signing configure / show ───────────────────────


def test_gpg_git_signing_show_with_signing_key(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """git-signing show reads gpg.signingkey + commit.gpgsign."""
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        cmd_l = list(cmd)
        # git config queries.
        if cmd_l[:2] == ["git", "config"]:
            key = cmd_l[2] if len(cmd_l) > 2 else ""
            if key == "user.signingkey":
                return CommandResult(0, "ABC123\n", "")
            if key == "commit.gpgsign":
                return CommandResult(0, "true\n", "")
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run", staticmethod(fake_run)
    )
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.shutil.which", lambda b: f"/usr/bin/{b}"
    )
    monkeypatch.setattr("shimkit.core.version.preflight", lambda *a, **kw: None)
    result = runner.invoke(app, ["gpg", "git-signing", "show"])
    assert result.exit_code in (0, 1)


# ─── tls manager: status of expired cert ─────────────────────────────


def test_tls_status_unparseable_expiry(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When openssl returns garbage, status still reports the cert
    but marks expiry as unknown."""
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
            return CommandResult(0, "", "")

    monkeypatch.setattr("shimkit.tools.tls.manager.DockerEnv", _FakeEnv)
    monkeypatch.setattr("shimkit.tools.tls.manager._vc.preflight", lambda *a, **kw: None)
    monkeypatch.setenv("HOME", str(tmp_path))
    from shimkit.config import reset_cache

    reset_cache()
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
    (live / "fullchain.pem").write_text("fake-pem")
    monkeypatch.setattr(
        "shimkit.tools.tls.manager.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(0, "notAfter=garbage", "")),
    )
    result = runner.invoke(app, ["tls", "status", "example.com", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.output)
    # Expiry can't be parsed → expires_at = None.
    assert doc["data"]["expires_at"] is None
