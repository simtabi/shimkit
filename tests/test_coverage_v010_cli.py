"""Coverage push: CLI surfaces of java, hosts, ssh, env.

Wires fake JavaManager / HostsManager / etc. so the Typer surface
gets exercised without invoking real subprocesses. The point is to
cover the command-dispatch lines, exit-code mapping, and option
plumbing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from shimkit.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── java/commands ─────────────────────────────────────────────────────


def _patch_java_manager(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> MagicMock:
    """Replace JavaManager.create().boot() with a configurable mock."""
    m = MagicMock()
    for k, v in overrides.items():
        setattr(m, k, v)

    class _Factory:
        @classmethod
        def create(cls) -> MagicMock:
            return m

    m.boot.return_value = m
    monkeypatch.setattr("shimkit.tools.java.commands.JavaManager", _Factory, raising=False)
    return m


def test_java_install_default_version_from_config(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    # We need JavaManager.create in BOTH commands and manager modules.
    # The actual import is local — patch at the right module.
    seen: dict[str, str] = {}

    class FakeMgr:
        @classmethod
        def create(cls):  # type: ignore[no-untyped-def]
            return cls()

        def boot(self):
            return self

        def install(self, version: str) -> bool:
            seen["version"] = version
            return True

    monkeypatch.setattr("shimkit.tools.java.manager.JavaManager", FakeMgr)
    result = runner.invoke(app, ["java", "install"])
    assert result.exit_code == 0
    # Default from config.
    assert seen["version"] == "21"


def test_java_install_explicit_version(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str] = {}

    class FakeMgr:
        @classmethod
        def create(cls):  # type: ignore[no-untyped-def]
            return cls()

        def boot(self):
            return self

        def install(self, version: str) -> bool:
            seen["version"] = version
            return True

    monkeypatch.setattr("shimkit.tools.java.manager.JavaManager", FakeMgr)
    result = runner.invoke(app, ["java", "install", "17"])
    assert result.exit_code == 0
    assert seen["version"] == "17"


def test_java_install_failure_exit_1(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeMgr:
        @classmethod
        def create(cls):  # type: ignore[no-untyped-def]
            return cls()

        def boot(self):
            return self

        def install(self, version: str) -> bool:
            return False

    monkeypatch.setattr("shimkit.tools.java.manager.JavaManager", FakeMgr)
    result = runner.invoke(app, ["java", "install", "21"])
    assert result.exit_code == 1


def test_java_list_empty(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMgr:
        @classmethod
        def create(cls):  # type: ignore[no-untyped-def]
            return cls()

        def boot(self):
            return self

        def list_installations(self):
            return []

    monkeypatch.setattr("shimkit.tools.java.manager.JavaManager", FakeMgr)
    result = runner.invoke(app, ["java", "list"])
    assert result.exit_code == 0
    assert "No Java installations" in result.output


def test_java_list_with_installations(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shimkit.tools.java.models import JavaInstallation

    class FakeMgr:
        @classmethod
        def create(cls):  # type: ignore[no-untyped-def]
            return cls()

        def boot(self):
            return self

        def list_installations(self):
            return [JavaInstallation("Homebrew", "openjdk-21.jdk", "/opt/x", True)]

    monkeypatch.setattr("shimkit.tools.java.manager.JavaManager", FakeMgr)
    result = runner.invoke(app, ["java", "list"])
    assert result.exit_code == 0
    assert "openjdk-21.jdk" in result.output


def test_java_switch_success(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMgr:
        @classmethod
        def create(cls):  # type: ignore[no-untyped-def]
            return cls()

        def boot(self):
            return self

        def switch_active(self, version: str) -> bool:
            return True

    monkeypatch.setattr("shimkit.tools.java.manager.JavaManager", FakeMgr)
    result = runner.invoke(app, ["java", "switch", "21"])
    assert result.exit_code == 0
    assert "Switched" in result.output


def test_java_switch_failure(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMgr:
        @classmethod
        def create(cls):  # type: ignore[no-untyped-def]
            return cls()

        def boot(self):
            return self

        def switch_active(self, version: str) -> bool:
            return False

    monkeypatch.setattr("shimkit.tools.java.manager.JavaManager", FakeMgr)
    result = runner.invoke(app, ["java", "switch", "21"])
    assert result.exit_code == 1


def test_java_upgrade_specific(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str | None] = {"version": "sentinel"}

    class FakeMgr:
        @classmethod
        def create(cls):  # type: ignore[no-untyped-def]
            return cls()

        def boot(self):
            return self

        def upgrade(self, version):  # type: ignore[no-untyped-def]
            seen["version"] = version
            return True

    monkeypatch.setattr("shimkit.tools.java.manager.JavaManager", FakeMgr)
    result = runner.invoke(app, ["java", "upgrade", "21"])
    assert result.exit_code == 0
    assert seen["version"] == "21"


def test_java_upgrade_all_when_no_arg(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str | None] = {"version": "sentinel"}

    class FakeMgr:
        @classmethod
        def create(cls):  # type: ignore[no-untyped-def]
            return cls()

        def boot(self):
            return self

        def upgrade(self, version):  # type: ignore[no-untyped-def]
            seen["version"] = version
            return True

    monkeypatch.setattr("shimkit.tools.java.manager.JavaManager", FakeMgr)
    result = runner.invoke(app, ["java", "upgrade"])
    assert result.exit_code == 0
    assert seen["version"] is None


def test_java_uninstall(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMgr:
        @classmethod
        def create(cls):  # type: ignore[no-untyped-def]
            return cls()

        def boot(self):
            return self

        def uninstall(self, version: str) -> bool:
            return True

    monkeypatch.setattr("shimkit.tools.java.manager.JavaManager", FakeMgr)
    result = runner.invoke(app, ["java", "uninstall", "21"])
    assert result.exit_code == 0


def test_java_remove_oracle_success(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeMgr:
        @classmethod
        def create(cls):  # type: ignore[no-untyped-def]
            return cls()

        def boot(self):
            return self

        def remove_oracle(self) -> bool:
            return True

    monkeypatch.setattr("shimkit.tools.java.manager.JavaManager", FakeMgr)
    result = runner.invoke(app, ["java", "remove-oracle"])
    assert result.exit_code == 0
    assert "removed" in result.output.lower()


def test_java_remove_oracle_noop(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeMgr:
        @classmethod
        def create(cls):  # type: ignore[no-untyped-def]
            return cls()

        def boot(self):
            return self

        def remove_oracle(self) -> bool:
            return False

    monkeypatch.setattr("shimkit.tools.java.manager.JavaManager", FakeMgr)
    result = runner.invoke(app, ["java", "remove-oracle"])
    assert result.exit_code == 1


# ─── hosts/manager apply_list + rollback ───────────────────────────────


def _force_linux_hosts(monkeypatch: pytest.MonkeyPatch, hosts_path: Path) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    # Redirect the hosts file path to a tmp location.

    class _FakeHostsCfg:
        hosts_path = str(hosts_path)
        max_entries_per_apply = 1000
        apply_list_severe_token = "APPLY-LIST"
        managed_block_marker = "# === shimkit-managed ==="

    monkeypatch.setattr(
        "shimkit.tools.hosts.manager.get_config",
        lambda: type(
            "Cfg", (), {"tools": type("Tools", (), {"hosts": _FakeHostsCfg()})()}
        )(),
    )


def test_hosts_apply_list_caps_at_max(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, runner: CliRunner
) -> None:
    """apply_list refuses lists above tools.hosts.max_entries_per_apply."""
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"
    hp.write_text("127.0.0.1 localhost\n", encoding="utf-8")

    class _Cap1:
        hosts_path = str(hp)
        max_entries_per_apply = 1
        apply_list_severe_token = "APPLY-LIST"
        managed_block_marker = "# === shimkit-managed ==="

    monkeypatch.setattr(
        "shimkit.tools.hosts.manager.get_config",
        lambda: type(
            "Cfg", (), {"tools": type("Tools", (), {"hosts": _Cap1()})()}
        )(),
    )
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    # Source file with 3 entries (above cap=1).
    src = tmp_path / "blocklist.txt"
    src.write_text(
        "0.0.0.0 ads.example.com\n0.0.0.0 tracker.test\n0.0.0.0 evil.test\n",
        encoding="utf-8",
    )
    mgr = HostsManager()
    mgr._hosts_path = hp
    rc = mgr.apply_list(str(src))
    assert rc == 1


def test_hosts_apply_list_dry_run_does_not_mutate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"
    hp.write_text("127.0.0.1 localhost\n", encoding="utf-8")

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
    src = tmp_path / "blocklist.txt"
    src.write_text("0.0.0.0 ads.example.com\n", encoding="utf-8")
    mgr = HostsManager()
    mgr._hosts_path = hp
    # Dry-run: returns 0, file isn't modified.
    rc = mgr.apply_list(str(src), dry_run=True)
    assert rc == 0
    assert "ads.example.com" not in hp.read_text()


def test_hosts_apply_list_local_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"
    hp.write_text("127.0.0.1 localhost\n", encoding="utf-8")

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
    # Stub _sudo_install to do a plain copy.
    def fake_install(self, src: Path, dst: Path) -> bool:  # type: ignore[no-untyped-def]
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return True

    monkeypatch.setattr(HostsManager, "_sudo_install", fake_install)
    src = tmp_path / "blocklist.txt"
    src.write_text("0.0.0.0 ads.example.com\n0.0.0.0 tracker.test\n", encoding="utf-8")
    mgr = HostsManager()
    mgr._hosts_path = hp
    rc = mgr.apply_list(str(src))
    assert rc == 0
    body = hp.read_text()
    assert "ads.example.com" in body
    assert "tracker.test" in body


def test_hosts_rollback_no_backups(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"
    hp.write_text("# empty\n")
    mgr = HostsManager()
    mgr._hosts_path = hp
    assert mgr.rollback() == 1  # no backups present


def test_hosts_rollback_restores_latest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.hosts.manager import HostsManager

    hp = tmp_path / "hosts"
    hp.write_text("current content\n", encoding="utf-8")
    older = tmp_path / "hosts.bak-20200101000000"
    older.write_text("old content\n", encoding="utf-8")
    newer = tmp_path / "hosts.bak-20260515000000"
    newer.write_text("newer content\n", encoding="utf-8")

    def fake_install(self, src: Path, dst: Path) -> bool:  # type: ignore[no-untyped-def]
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return True

    monkeypatch.setattr(HostsManager, "_sudo_install", fake_install)
    mgr = HostsManager()
    mgr._hosts_path = hp
    rc = mgr.rollback()
    assert rc == 0
    assert hp.read_text() == "newer content\n"


# ─── ssh agent_add / config_show ───────────────────────────────────────


def test_ssh_agent_add_missing_key(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(
        app, ["ssh", "agent", "add", str(tmp_path / "nonexistent")]
    )
    assert result.exit_code == 1


def test_ssh_agent_add_dry_run(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    key = tmp_path / "id_ed25519"
    key.write_text("private")
    result = runner.invoke(app, ["ssh", "agent", "add", str(key), "--dry-run"])
    assert result.exit_code == 0


def test_ssh_config_show_missing_file(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(app, ["ssh", "config", "show"])
    assert result.exit_code == 0
    assert "not present" in result.output.lower() or "not found" in result.output.lower()


def test_ssh_config_show_existing_file(
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
    (ssh_dir / "config").write_text("Host example\n    User someone\n", encoding="utf-8")
    result = runner.invoke(app, ["ssh", "config", "show"])
    assert result.exit_code == 0
    assert "Host example" in result.output


# ─── env manager redaction ─────────────────────────────────────────────


def test_env_show_redacts_secrets(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_NAME=myapp\nDB_PASSWORD=supersecret\nAPI_KEY=topsecret\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["env", "show", str(env_file)])
    assert result.exit_code == 0
    assert "myapp" in result.output
    # Secret keys should be redacted.
    assert "supersecret" not in result.output
    assert "topsecret" not in result.output


def test_env_show_json_includes_keys(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=1\nBAR=2\n", encoding="utf-8")
    result = runner.invoke(app, ["env", "show", str(env_file), "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.output)
    keys = {entry["key"] for entry in doc["data"]["entries"]}
    assert keys == {"FOO", "BAR"}


def test_env_show_reveal_unredacts(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DB_PASSWORD=supersecret\n", encoding="utf-8")
    result = runner.invoke(app, ["env", "show", str(env_file), "--reveal", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.output)
    entry = doc["data"]["entries"][0]
    assert entry["value"] == "supersecret"
    assert entry["redacted"] is False


# ─── docker_clean status (read-only) ───────────────────────────────────


def test_docker_clean_status_requires_docker(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Without docker on PATH, status should exit 69.
    monkeypatch.setattr("shimkit.core.version.shutil.which", lambda _b: None)
    result = runner.invoke(app, ["docker-clean", "status"])
    assert result.exit_code == 69
