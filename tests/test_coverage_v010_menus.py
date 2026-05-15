"""Coverage for interactive menu paths in java and ssh managers.

These paths historically went uncovered because they call Menu.select
which only runs in an interactive TTY. We stub Menu so the test
deterministically picks an option and the underlying handler runs.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from shimkit.core import CommandResult
from shimkit.core import platform as _plat


def _booted_java(monkeypatch: pytest.MonkeyPatch):
    from shimkit.tools.java import manager as _jmgr

    monkeypatch.setattr(
        _plat.Platform, "detect", classmethod(lambda cls: _plat.Platform(system="Linux"))
    )

    class FakeShell:
        @classmethod
        def detect(cls, _platform):  # type: ignore[no-untyped-def]
            sh = MagicMock()
            sh.config_file = "/home/user/.bashrc"
            sh.description = "bash"
            sh.ensure_config_exists.return_value = sh
            return sh

    monkeypatch.setattr("shimkit.tools.java.manager.Shell", FakeShell)
    m = _jmgr.JavaManager.create().boot()
    m._brew = MagicMock()
    m._scanner = MagicMock()
    m._installer = MagicMock()
    m._remover = MagicMock()
    m._shell.config_file = "/home/user/.bashrc"
    return m


# ─── java _menu_install branches ─────────────────────────────────────


def test_menu_install_picks_new_version(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = ["17"]
    m._installer.install.return_value = True
    m._installer.verify.return_value = True
    m._brew.installed = True
    # The select returns the option with version 21.
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.select",
        lambda *a, **kw: "Java 21 (LTS)",
    )
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.confirm",
        lambda *a, **kw: True,
    )
    m._menu_install()
    m._installer.install.assert_called_with("21")


def test_menu_install_picks_existing_then_reinstalls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = ["21"]
    m._installer.reinstall.return_value = True
    m._installer.verify.return_value = True
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.select",
        lambda *a, **kw: "Java 21 [✓ installed]",
    )
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.confirm",
        lambda *a, **kw: True,
    )
    m._menu_install()
    m._installer.reinstall.assert_called_with("21")


def test_menu_install_user_cancels_back(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = []
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.select",
        lambda *a, **kw: "← Back",
    )
    m._menu_install()  # short-circuits cleanly
    m._installer.install.assert_not_called()


def test_menu_install_user_declines_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = []
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.select",
        lambda *a, **kw: "Java 21 (LTS)",
    )
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.confirm",
        lambda *a, **kw: False,
    )
    m._menu_install()
    m._installer.install.assert_not_called()


def test_menu_install_bootstraps_brew_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = []
    m._brew.installed = False
    m._brew.install_self.return_value = True
    m._installer.install.return_value = True
    m._installer.verify.return_value = True
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.select",
        lambda *a, **kw: "Java 21 (LTS)",
    )
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.confirm",
        lambda *a, **kw: True,
    )
    m._menu_install()
    m._brew.install_self.assert_called_once()


def test_menu_install_aborts_when_brew_install_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = []
    m._brew.installed = False
    m._brew.install_self.return_value = False
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.select",
        lambda *a, **kw: "Java 21 (LTS)",
    )
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.confirm",
        lambda *a, **kw: True,
    )
    m._menu_install()
    m._installer.install.assert_not_called()


# ─── java _menu_upgrade selects-then-upgrades ────────────────────────


def test_menu_upgrade_selects_outdated(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = ["21"]
    m._brew.outdated_java.return_value = [{"name": "openjdk@21"}]
    m._installer.upgrade.return_value = True
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.checkbox",
        lambda *a, **kw: ["openjdk@21  ⚠ update available"],
    )
    m._menu_upgrade()
    m._installer.upgrade.assert_called_with("21")


def test_menu_upgrade_user_cancels(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = ["21"]
    m._brew.outdated_java.return_value = [{"name": "openjdk@21"}]
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.checkbox",
        lambda *a, **kw: [],
    )
    m._menu_upgrade()
    m._installer.upgrade.assert_not_called()


# ─── java _menu_switch ────────────────────────────────────────────────


def test_menu_switch_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = ["17", "21"]
    m._installer.switch.return_value = True
    m._brew.prefix = "/opt/homebrew"
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.select",
        lambda *a, **kw: "openjdk@21",
    )
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.confirm",
        lambda *a, **kw: True,
    )
    monkeypatch.setattr(
        "shimkit.tools.java.manager.java_home_for",
        lambda prefix, v, is_macos: f"{prefix}/openjdk@{v}",
    )
    m._menu_switch()
    m._installer.switch.assert_called_with("21")


def test_menu_switch_back_cancels(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = ["17", "21"]
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.select",
        lambda *a, **kw: "← Back",
    )
    m._menu_switch()
    m._installer.switch.assert_not_called()


# ─── java _menu_remove_oracle happy path ─────────────────────────────


def test_menu_remove_oracle_with_install(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.java.models import JavaInstallation

    m = _booted_java(monkeypatch)
    m._remover.available.return_value = True
    m._remover.remove.return_value = True
    m._scanner.scan.return_value = [
        JavaInstallation("Oracle", "jdk-22.jdk", "/Library/Java/X", False)
    ]
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.confirm",
        lambda *a, **kw: True,
    )
    m._menu_remove_oracle()
    m._remover.remove.assert_called_once()


# ─── java _menu_uninstall happy path ─────────────────────────────────


def test_menu_uninstall_with_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = ["21"]
    m._installer.uninstall.return_value = True
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.select",
        lambda *a, **kw: "openjdk@21",
    )
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.confirm",
        lambda *a, **kw: True,
    )
    m._menu_uninstall()
    m._installer.uninstall.assert_called_with("21")


def test_menu_uninstall_declines_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = ["21"]
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.select",
        lambda *a, **kw: "openjdk@21",
    )
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.confirm",
        lambda *a, **kw: False,
    )
    m._menu_uninstall()
    m._installer.uninstall.assert_not_called()


# ─── java run() loop ─────────────────────────────────────────────────


def test_run_exits_on_user_quit(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.active_version_string = "openjdk 21\n"
    m._scanner.scan.return_value = []
    # Disable auto-checks.
    monkeypatch.setattr(m, "check_self_update", lambda: m)
    monkeypatch.setattr(m, "check_java_updates", lambda: m)

    class _SpinCtx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("shimkit.tools.java.manager.UI.spinner", lambda _msg: _SpinCtx())
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.select",
        lambda *a, **kw: "Exit",
    )
    m.run()  # exits cleanly


def test_run_handles_none_select(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_java(monkeypatch)
    m._scanner.active_version_string = "openjdk 21\n"
    monkeypatch.setattr(m, "check_self_update", lambda: m)
    monkeypatch.setattr(m, "check_java_updates", lambda: m)

    class _SpinCtx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("shimkit.tools.java.manager.UI.spinner", lambda _msg: _SpinCtx())
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.select",
        lambda *a, **kw: None,
    )
    m.run()  # None choice exits the loop


# ─── ssh manager run() menu ───────────────────────────────────────────


def test_ssh_run_loops_then_quits(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Verify SshManager.run() dispatches each menu option once before Quit."""
    from shimkit.core.platform import Platform
    from shimkit.tools.ssh.manager import SshManager

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir(mode=0o700)
    mgr = SshManager.create().boot()
    # Stub each method called from run().
    called: list[str] = []
    monkeypatch.setattr(mgr, "keys_list", lambda: called.append("keys") or 0)
    monkeypatch.setattr(mgr, "agent_status", lambda: called.append("agent") or 0)
    monkeypatch.setattr(mgr, "known_hosts_audit", lambda: called.append("known") or 0)
    monkeypatch.setattr(mgr, "perms_audit", lambda: called.append("perms") or 0)
    # Walk the user through every choice then quit.
    sequence = iter(
        [
            "List keys",
            "ssh-agent status",
            "Audit known_hosts duplicates",
            "Audit ~/.ssh permissions",
            "Quit",
        ]
    )
    monkeypatch.setattr(
        "shimkit.tools.ssh.manager.Menu.select",
        lambda *a, **kw: next(sequence),
    )
    mgr.run()
    assert called == ["keys", "agent", "known", "perms"]


def test_ssh_run_exits_on_none(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.ssh.manager import SshManager

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".ssh").mkdir(mode=0o700)
    mgr = SshManager.create().boot()
    monkeypatch.setattr(
        "shimkit.tools.ssh.manager.Menu.select",
        lambda *a, **kw: None,
    )
    mgr.run()  # exits


# ─── ssh manager: keys_generate with happy path ──────────────────────


def test_ssh_keys_generate_creates_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.ssh.manager import SshManager

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    mgr = SshManager.create().boot()
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.ssh.manager.CommandRunner.run", staticmethod(fake_run)
    )
    assert mgr.keys_generate("id_test", key_type="ed25519") == 0
    assert seen[0][:3] == ["ssh-keygen", "-t", "ed25519"]


def test_ssh_keys_generate_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.ssh.manager import SshManager

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    mgr = SshManager.create().boot()
    monkeypatch.setattr(
        "shimkit.tools.ssh.manager.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(1, "", "permission denied")),
    )
    assert mgr.keys_generate("id_test") == 1


def test_ssh_keys_rotate_missing_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.ssh.manager import SshManager

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    mgr = SshManager.create().boot()
    assert mgr.keys_rotate("missing") == 1


def test_ssh_keys_rotate_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.ssh.manager import SshManager

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir(mode=0o700)
    (ssh_dir / "id_old").write_text("private")
    (ssh_dir / "id_old.pub").write_text("ssh-rsa AAAA")
    mgr = SshManager.create().boot()
    # Dry-run: does NOT rename files, does NOT shell out.
    assert mgr.keys_rotate("id_old", dry_run=True) == 0
    assert (ssh_dir / "id_old").exists()
