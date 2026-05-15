"""Final coverage push: deep targeted tests for the largest remaining
managers — adguard, ssh, db, hosts, dns. Each test exercises a
specific method by building a minimally-configured manager and
mocking its boundaries.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── adguard manager: scan / verify / ports_show / ports_set ──────────


def _adguard_with_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from shimkit.core import platform as _plat
    from shimkit.tools.adguard import manager as _amgr
    from shimkit.tools.adguard.models import AdGuardInstall

    monkeypatch.setattr(
        _plat.Platform,
        "detect",
        classmethod(lambda cls: _plat.Platform(system="Linux", machine="x86_64")),
    )
    yaml = tmp_path / "agh.yaml"
    yaml.write_text("# minimal\n")
    inst = AdGuardInstall(
        binary=tmp_path / "AdGuardHome",
        yaml_path=yaml,
        install_root=tmp_path,
    )
    mgr = _amgr.AdGuardManager()
    mgr._platform = _plat.Platform(system="Linux", machine="x86_64")
    mgr._install = inst
    return mgr


def test_adguard_scan_no_conflicts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.adguard import yaml_editor as _ye

    monkeypatch.setattr(_ye, "read_ports", lambda _p: (53, 80))
    monkeypatch.setattr("shimkit.tools.adguard.manager.ports.owners_of", lambda *a: [])
    mgr = _adguard_with_install(monkeypatch, tmp_path)
    assert mgr.scan() == 0


def test_adguard_scan_with_conflicts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.adguard import yaml_editor as _ye
    from shimkit.tools.adguard.models import PortOwner

    monkeypatch.setattr(_ye, "read_ports", lambda _p: (53, 80))
    monkeypatch.setattr(
        "shimkit.tools.adguard.manager.ports.owners_of",
        lambda port, proto: [PortOwner(pid=42, name="dnsmasq", unit="dnsmasq.service")]
        if port == 53
        else [],
    )
    monkeypatch.setattr("shimkit.tools.adguard.manager.ports.is_agh_process", lambda _: False)
    mgr = _adguard_with_install(monkeypatch, tmp_path)
    # JSON path
    captured: list[str] = []
    monkeypatch.setattr(
        "shimkit.tools.adguard.manager.emit_json", lambda ev: captured.append(ev.status)
    )
    mgr.scan(json_out=True)
    assert "warning" in captured


def test_adguard_verify_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from shimkit.tools.adguard import api as _api
    from shimkit.tools.adguard import yaml_editor as _ye

    monkeypatch.setattr(_ye, "read_ports", lambda _p: (53, 80))
    monkeypatch.setattr(_api, "status", lambda timeout=5: {"running": True})
    mgr = _adguard_with_install(monkeypatch, tmp_path)
    monkeypatch.setattr(mgr, "_loopback_dns_test", lambda port, timeout=3.0: True)
    assert mgr.verify() == 0


def test_adguard_verify_fail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from shimkit.tools.adguard import api as _api
    from shimkit.tools.adguard import yaml_editor as _ye

    monkeypatch.setattr(_ye, "read_ports", lambda _p: (53, 80))
    monkeypatch.setattr(_api, "status", lambda timeout=5: None)
    mgr = _adguard_with_install(monkeypatch, tmp_path)
    monkeypatch.setattr(mgr, "_loopback_dns_test", lambda port, timeout=3.0: False)
    assert mgr.verify() == 1


def test_adguard_loopback_dns_tcp_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When dnspython is missing, falls back to a TCP connect."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):  # type: ignore[no-untyped-def]
        if name == "dns.resolver" or name.startswith("dns."):
            raise ImportError("no dnspython")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    # Make the fallback connect-attempt fail.
    def fake_create_connection(*a, **kw):  # type: ignore[no-untyped-def]
        raise OSError("refused")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    mgr = _adguard_with_install(monkeypatch, tmp_path)
    assert mgr._loopback_dns_test(53) is False


def test_adguard_ports_show_no_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.adguard import manager as _amgr

    mgr = _amgr.AdGuardManager()
    mgr._install = None
    assert mgr.ports_show() == 69


def test_adguard_ports_show_outputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.adguard import yaml_editor as _ye

    monkeypatch.setattr(_ye, "read_ports", lambda _p: (5353, 8080))
    mgr = _adguard_with_install(monkeypatch, tmp_path)
    captured: list[str] = []
    monkeypatch.setattr("shimkit.tools.adguard.manager.UI.line", lambda msg: captured.append(msg))
    assert mgr.ports_show() == 0
    assert any("5353" in m for m in captured)
    assert any("8080" in m for m in captured)


def test_adguard_ports_set_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mgr = _adguard_with_install(monkeypatch, tmp_path)
    assert mgr.ports_set(dns=5353, http=8080, dry_run=True) == 0


def test_adguard_ports_set_no_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.tools.adguard import manager as _amgr

    mgr = _amgr.AdGuardManager()
    mgr._install = None
    assert mgr.ports_set(dns=5353, http=8080) == 69


def test_adguard_ports_set_yaml_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When API isn't reachable, falls back to yaml + systemd lifecycle."""
    from shimkit.core import systemd as _sd
    from shimkit.tools.adguard import api as _api
    from shimkit.tools.adguard import yaml_editor as _ye

    monkeypatch.setattr(_api, "is_reachable", lambda timeout=3.0: False)
    monkeypatch.setattr(_ye, "set_ports", lambda _p, dns, http: (dns, http))
    started: list[str] = []
    stopped: list[str] = []
    monkeypatch.setattr(_sd.Systemd, "start", staticmethod(lambda u: started.append(u) or CommandResult(0, "", "")))
    monkeypatch.setattr(_sd.Systemd, "stop", staticmethod(lambda u: stopped.append(u) or CommandResult(0, "", "")))
    mgr = _adguard_with_install(monkeypatch, tmp_path)
    assert mgr.ports_set(dns=5353, http=8080) == 0
    assert stopped == ["AdGuardHome"]
    assert started == ["AdGuardHome"]


# ─── ssh manager — agent_status (JSON), keys_list, perms_audit ───────


def _ssh_setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir(mode=0o700)
    return ssh_dir


def test_ssh_agent_status_unreachable_json(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ssh_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "shimkit.tools.ssh.manager.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(2, "", "agent not running")),
    )
    result = runner.invoke(app, ["ssh", "agent", "status", "--json"])
    # exit 1 (agent unreachable) is intentional.
    assert result.exit_code == 1
    doc = json.loads(result.output)
    assert doc["data"]["agent_running"] is False


def test_ssh_known_hosts_audit_missing_file(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ssh_setup(monkeypatch, tmp_path)
    result = runner.invoke(app, ["ssh", "known-hosts", "audit", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.output)
    assert doc["data"]["duplicates"] == []


def test_ssh_known_hosts_prune_missing_file(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ssh_setup(monkeypatch, tmp_path)
    result = runner.invoke(app, ["ssh", "known-hosts", "prune", "--yes"])
    assert result.exit_code == 0
    assert "nothing to prune" in result.output.lower() or "not present" in result.output.lower()


def test_ssh_known_hosts_prune_dry_run(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ssh_dir = _ssh_setup(monkeypatch, tmp_path)
    kh = ssh_dir / "known_hosts"
    # Two duplicate lines for the same host.
    kh.write_text(
        "github.com ssh-rsa AAAA1\n"
        "github.com ssh-rsa AAAA1\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["ssh", "known-hosts", "prune", "--yes", "--dry-run"])
    assert result.exit_code == 0
    # File untouched.
    assert kh.read_text().count("\n") == 2


def test_ssh_keys_list_via_cli(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ssh_dir = _ssh_setup(monkeypatch, tmp_path)
    (ssh_dir / "id_ed25519").write_text("private")
    (ssh_dir / "id_ed25519.pub").write_text(
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA me@host"
    )
    result = runner.invoke(app, ["ssh", "keys", "list", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.output)
    keys = doc["data"]["keys"]
    assert any(k["name"] == "id_ed25519" for k in keys)


# ─── db manager — ls ──────────────────────────────────────────────────


def test_db_ls_empty(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:

    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.core.version.preflight", lambda *a, **kw: None)
    import sys as _sys
    import types

    fake = types.ModuleType("docker.errors")

    class _NotFound(Exception):  # noqa: N818
        pass

    fake.NotFound = _NotFound  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "docker.errors", fake)

    client = MagicMock()
    client.containers.list.return_value = []
    monkeypatch.setattr("shimkit.core.docker._from_env", lambda: client)
    result = runner.invoke(app, ["db", "ls", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.output)
    assert doc["data"]["containers"] == []


# ─── hosts manager — show + run interactive quit path ─────────────────


def test_hosts_show_via_cli(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """hosts show enumerates entries from the hosts file."""
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    hp = tmp_path / "hosts"
    hp.write_text(
        "127.0.0.1 localhost\n"
        "10.0.0.1 myhost  # custom\n",
        encoding="utf-8",
    )

    class _Cfg:
        hosts_path = str(hp)
        max_entries_per_apply = 1000
        apply_list_severe_token = "APPLY-LIST"
        managed_block_marker = "# === shimkit-managed ==="

    monkeypatch.setattr(
        "shimkit.tools.hosts.manager.get_config",
        lambda: type(
            "Cfg", (), {"tools": type("Tools", (), {"hosts": _Cfg()})()}
        )(),
    )
    result = runner.invoke(app, ["hosts", "show", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.output)
    names = {e["name"] for e in doc["data"]["entries"]}
    assert "localhost" in names
    assert "myhost" in names


def test_hosts_show_empty(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    hp = tmp_path / "hosts"
    hp.write_text("# only comments\n", encoding="utf-8")

    class _Cfg:
        hosts_path = str(hp)
        max_entries_per_apply = 1000
        apply_list_severe_token = "APPLY-LIST"
        managed_block_marker = "# === shimkit-managed ==="

    monkeypatch.setattr(
        "shimkit.tools.hosts.manager.get_config",
        lambda: type(
            "Cfg", (), {"tools": type("Tools", (), {"hosts": _Cfg()})()}
        )(),
    )
    result = runner.invoke(app, ["hosts", "show"])
    assert result.exit_code == 0
    assert "No entries" in result.output


# ─── ports manager via CLI ────────────────────────────────────────────


def test_ports_list_empty(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ports list --json with no listeners."""
    import sys as _sys
    import types

    fake = types.ModuleType("psutil")

    def net_connections(*, kind):  # type: ignore[no-untyped-def]
        return []

    fake.net_connections = net_connections
    fake.CONN_LISTEN = "LISTEN"
    fake.AccessDenied = type("AccessDenied", (Exception,), {})
    fake.NoSuchProcess = type("NoSuchProcess", (Exception,), {})

    class _Proc:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def name(self) -> str:
            return "?"

    fake.Process = _Proc
    monkeypatch.setitem(_sys.modules, "psutil", fake)
    result = runner.invoke(app, ["ports", "show", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.output)
    # The exact key name varies — just check the JSON parses and reports ok.
    assert doc["status"] == "ok"


# ─── web nginx vhost generate ─────────────────────────────────────────


def test_web_nginx_vhost_generate_static(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "generate",
            "--name",
            "myapp",
            "--domain",
            "example.com",
            "--root",
            str(tmp_path),
            "--flavor",
            "static",
        ],
    )
    assert result.exit_code == 0
    assert "example.com" in result.output
    assert "server_name" in result.output


def test_web_nginx_vhost_generate_php(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "generate",
            "--name",
            "myapp",
            "--domain",
            "example.com",
            "--root",
            str(tmp_path),
            "--flavor",
            "php",
            "--php-version",
            "8.3",
        ],
    )
    assert result.exit_code == 0
    assert "fastcgi" in result.output


def test_web_nginx_vhost_generate_unknown_flavor(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "generate",
            "--name",
            "x",
            "--domain",
            "example.com",
            "--root",
            str(tmp_path),
            "--flavor",
            "java",  # not supported
        ],
    )
    assert result.exit_code != 0


# ─── logs via CLI ─────────────────────────────────────────────────────


def test_logs_help_lists_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["logs", "--help"])
    assert result.exit_code == 0
    # At least one of the read-only subcommands.
    assert any(sub in result.output for sub in ("show", "tail", "grep"))
