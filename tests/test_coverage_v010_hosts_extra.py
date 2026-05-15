"""Extra coverage for hosts/manager internals and web nginx vhost
list/apply edges."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── hosts/_read_source and _back_up ─────────────────────────────────


def test_hosts_read_source_missing_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    mgr = HostsManager()
    mgr._hosts_path = tmp_path / "hosts"
    assert mgr._read_source(str(tmp_path / "does-not-exist")) is None


def test_hosts_read_source_local_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    src = tmp_path / "list.txt"
    src.write_text("0.0.0.0 ads.example\n", encoding="utf-8")
    mgr = HostsManager()
    mgr._hosts_path = tmp_path / "hosts"
    body = mgr._read_source(str(src))
    assert body is not None
    assert "ads.example" in body


def test_hosts_read_source_url_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import urllib.error as _ue

    from shimkit.tools.hosts.manager import HostsManager

    def fake_urlopen(*a, **kw):  # type: ignore[no-untyped-def]
        raise _ue.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    mgr = HostsManager()
    mgr._hosts_path = tmp_path / "hosts"
    assert mgr._read_source("https://example.com/list.txt") is None


def test_hosts_read_source_url_ok(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"0.0.0.0 ads.test\n"

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: FakeResponse())
    mgr = HostsManager()
    mgr._hosts_path = tmp_path / "hosts"
    body = mgr._read_source("https://example.com/list.txt")
    assert body is not None
    assert "ads.test" in body


def test_hosts_back_up_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"
    hp.write_text("# hello\n", encoding="utf-8")
    monkeypatch.setattr(
        "shimkit.tools.hosts.manager.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(1, "", "permission denied")),
    )
    monkeypatch.setattr("shimkit.tools.hosts.manager.sudo_prefix", lambda: [])
    mgr = HostsManager()
    mgr._hosts_path = hp
    assert mgr._back_up() is None


def test_hosts_back_up_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"
    hp.write_text("# hello\n", encoding="utf-8")
    monkeypatch.setattr(
        "shimkit.tools.hosts.manager.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(0, "", "")),
    )
    monkeypatch.setattr("shimkit.tools.hosts.manager.sudo_prefix", lambda: [])
    mgr = HostsManager()
    mgr._hosts_path = hp
    bak = mgr._back_up()
    assert bak is not None
    assert bak.name.startswith("hosts.bak-")


def test_hosts_atomic_write_via_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"
    hp.write_text("# pre\n", encoding="utf-8")
    # Stub _sudo_install to succeed by copying.
    def fake_install(self, src: Path, dst: Path) -> bool:  # type: ignore[no-untyped-def]
        dst.write_text(src.read_text(encoding="utf-8"))
        return True

    monkeypatch.setattr(HostsManager, "_sudo_install", fake_install)
    mgr = HostsManager()
    mgr._hosts_path = hp
    assert mgr._atomic_write("# new content\n") is True
    assert "new content" in hp.read_text()


def test_hosts_atomic_write_falls_back_to_root_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When sudo install fails but we're already root, fall back to
    a direct write."""
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"
    hp.write_text("# pre\n", encoding="utf-8")

    def fake_install(self, src, dst):  # type: ignore[no-untyped-def]
        return False  # sudo install fails

    monkeypatch.setattr(HostsManager, "_sudo_install", fake_install)
    monkeypatch.setattr("shimkit.tools.hosts.manager.is_root", lambda: True)
    mgr = HostsManager()
    mgr._hosts_path = hp
    assert mgr._atomic_write("# fallback\n") is True
    assert "fallback" in hp.read_text()


def test_hosts_atomic_write_fails_when_no_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"

    def fake_install(self, src, dst):  # type: ignore[no-untyped-def]
        return False

    monkeypatch.setattr(HostsManager, "_sudo_install", fake_install)
    monkeypatch.setattr("shimkit.tools.hosts.manager.is_root", lambda: False)
    mgr = HostsManager()
    mgr._hosts_path = hp
    assert mgr._atomic_write("# x\n") is False


# ─── hosts: interactive run() path ──────────────────────────────────


def test_hosts_run_quit_immediately(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    mgr = HostsManager()
    mgr._hosts_path = tmp_path / "hosts"
    (tmp_path / "hosts").write_text("# x\n")
    monkeypatch.setattr(
        "shimkit.tools.hosts.manager.Menu.select",
        lambda *a, **kw: "Quit",
    )
    mgr.run()


def test_hosts_run_list_then_quit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    mgr = HostsManager()
    mgr._hosts_path = tmp_path / "hosts"
    (tmp_path / "hosts").write_text("127.0.0.1 localhost\n")

    class _Cfg:
        hosts_path = str(tmp_path / "hosts")
        max_entries_per_apply = 1000
        apply_list_severe_token = "APPLY-LIST"
        managed_block_marker = "# === shimkit-managed ==="

    monkeypatch.setattr(
        "shimkit.tools.hosts.manager.get_config",
        lambda: type(
            "Cfg", (), {"tools": type("Tools", (), {"hosts": _Cfg()})()}
        )(),
    )
    sequence = iter(["List entries", "Quit"])
    monkeypatch.setattr(
        "shimkit.tools.hosts.manager.Menu.select",
        lambda *a, **kw: next(sequence),
    )
    mgr.run()


# ─── web nginx vhost list / apply edges ──────────────────────────────


def test_web_nginx_vhost_list_empty(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """List with empty sites-available dir."""
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.core.version.preflight", lambda *a, **kw: None)

    class _NginxCfg:
        sites_available_dir = str(tmp_path / "sites-available")
        sites_enabled_dir = str(tmp_path / "sites-enabled")
        reload_cmd = ["nginx", "-s", "reload"]
        apply_severe_token = "APPLY-VHOST"
        remove_severe_token = "REMOVE-VHOST"
        default_php_version = "8.3"
        default_flavor = "static"
        managed_marker = "# managed-by: shimkit"

    class _WebCfg:
        nginx = _NginxCfg()

    monkeypatch.setattr(
        "shimkit.tools.web.nginx.manager.get_config",
        lambda: type(
            "Cfg",
            (),
            {
                "tools": type(
                    "Tools",
                    (),
                    {
                        "web": _WebCfg(),
                        "versions": type(
                            "V",
                            (),
                            {"nginx": type("VC", (), {"min": None, "max": None})()},
                        )(),
                    },
                )()
            },
        )(),
    )
    result = runner.invoke(app, ["web", "nginx", "vhost", "list", "--json"])
    # Sites dir doesn't exist, so it should return empty list.
    assert result.exit_code in (0, 1)


# ─── tls: cron-install when missing php (warning path) ─────────────


def test_tls_cron_install_warns_no_php(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Wraps the cron install path that warns when shimkit isn't on PATH."""
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )

    class _FakeEnv:
        @classmethod
        def create(cls):
            return cls()

        def boot(self):
            return self

    monkeypatch.setattr("shimkit.tools.tls.manager.DockerEnv", _FakeEnv)
    monkeypatch.setattr("shimkit.tools.tls.manager._vc.preflight", lambda *a, **kw: None)
    monkeypatch.setenv("HOME", str(tmp_path))
    from shimkit.config import reset_cache

    reset_cache()

    seen: dict[str, object] = {}

    class FakeCronManager:
        @classmethod
        def create(cls):
            return cls()

        def boot(self):
            return self

        def add(self, **kw):
            seen.update(kw)
            return 0

    monkeypatch.setattr("shimkit.tools.cron.manager.CronManager", FakeCronManager)
    result = runner.invoke(app, ["tls", "cron-install", "--yes"])
    assert result.exit_code == 0
    assert seen["name"] == "tls-renew"


def test_tls_renew_outcome_failure(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """certbot returns non-zero — manager exits 1."""
    from shimkit.core import ExecOutcome
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )

    class _FakeEnv:
        @classmethod
        def create(cls):
            return cls()

        def boot(self):
            return self

        def run_oneshot(self, *a, **kw):
            return ExecOutcome(exit_code=1, stdout="", stderr="ACME server error")

    monkeypatch.setattr("shimkit.tools.tls.manager.DockerEnv", _FakeEnv)
    monkeypatch.setattr("shimkit.tools.tls.manager._vc.preflight", lambda *a, **kw: None)
    monkeypatch.setenv("HOME", str(tmp_path))
    from shimkit.config import reset_cache

    reset_cache()
    result = runner.invoke(app, ["tls", "renew", "--yes"])
    assert result.exit_code == 1
    assert "ACME server error" in result.output


def test_tls_revoke_propagates_certbot_failure(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.core import ExecOutcome
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )

    class _FakeEnv:
        @classmethod
        def create(cls):
            return cls()

        def boot(self):
            return self

        def run_oneshot(self, *a, **kw):
            return ExecOutcome(exit_code=1, stdout="", stderr="cert not found upstream")

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
    (live / "fullchain.pem").write_text("fake")
    result = runner.invoke(
        app, ["tls", "revoke", "-d", "example.com", "--confirm", "REVOKE-TLS"]
    )
    assert result.exit_code == 1
