"""Coverage for ``shimkit.tools.java.manager``.

The manager wires Platform, Shell, Brew, JavaScanner, JavaInstaller,
and OracleRemover. We mock at the component boundary — every
test exercises a single manager method with stubs for the others.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from shimkit.core import platform as _plat
from shimkit.tools.java import manager as _jmgr
from shimkit.tools.java.models import JavaInstallation

# ─── boot ───────────────────────────────────────────────────────────────


def test_boot_exits_on_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _plat.Platform, "detect", classmethod(lambda cls: _plat.Platform(system="Windows"))
    )
    with pytest.raises(SystemExit) as exc:
        _jmgr.JavaManager.create().boot()
    assert exc.value.code == 1


def test_boot_wires_components_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _plat.Platform, "detect", classmethod(lambda cls: _plat.Platform(system="Linux"))
    )

    class FakeShell:
        @classmethod
        def detect(cls, _platform):  # type: ignore[no-untyped-def]
            sh = MagicMock()
            sh.ensure_config_exists.return_value = sh
            return sh

    monkeypatch.setattr("shimkit.tools.java.manager.Shell", FakeShell)
    m = _jmgr.JavaManager.create().boot()
    assert m._platform is not None
    assert m._brew is not None
    assert m._scanner is not None
    assert m._installer is not None
    assert m._remover is not None


# ─── helpers ────────────────────────────────────────────────────────────


def _booted_manager(monkeypatch: pytest.MonkeyPatch) -> _jmgr.JavaManager:
    monkeypatch.setattr(
        _plat.Platform, "detect", classmethod(lambda cls: _plat.Platform(system="Linux"))
    )

    class FakeShell:
        @classmethod
        def detect(cls, _platform):  # type: ignore[no-untyped-def]
            sh = MagicMock()
            sh.description = "bash"
            sh.config_file = "/home/user/.bashrc"
            sh.ensure_config_exists.return_value = sh
            return sh

    monkeypatch.setattr("shimkit.tools.java.manager.Shell", FakeShell)
    m = _jmgr.JavaManager.create().boot()
    # Replace component instances with mocks so each test isolates one call.
    m._brew = MagicMock()
    m._scanner = MagicMock()
    m._installer = MagicMock()
    m._remover = MagicMock()
    return m


# ─── install ────────────────────────────────────────────────────────────


def test_install_when_brew_missing_bootstraps_brew(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_manager(monkeypatch)
    m._brew.installed = False
    m._brew.install_self.return_value = True
    m._installer.install.return_value = True
    m._installer.verify.return_value = True
    assert m.install("21") is True
    m._brew.install_self.assert_called_once()
    m._installer.install.assert_called_with("21")


def test_install_aborts_when_brew_bootstrap_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _booted_manager(monkeypatch)
    m._brew.installed = False
    m._brew.install_self.return_value = False
    assert m.install("21") is False


def test_install_returns_false_when_installer_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _booted_manager(monkeypatch)
    m._brew.installed = True
    m._installer.install.return_value = False
    assert m.install("21") is False


def test_install_verify_failure_still_returns_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _booted_manager(monkeypatch)
    m._brew.installed = True
    m._installer.install.return_value = True
    m._installer.verify.return_value = False
    assert m.install("21") is True


# ─── uninstall ──────────────────────────────────────────────────────────


def test_uninstall_clears_java_home_when_matching(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAVA_HOME", "/opt/openjdk@21/something")
    m = _booted_manager(monkeypatch)
    m._installer.uninstall.return_value = True
    assert m.uninstall("21") is True
    import os as _os

    assert _os.environ.get("JAVA_HOME") is None


def test_uninstall_keeps_java_home_when_not_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JAVA_HOME", "/opt/openjdk@17/something")
    m = _booted_manager(monkeypatch)
    m._installer.uninstall.return_value = True
    assert m.uninstall("21") is True
    import os as _os

    assert _os.environ.get("JAVA_HOME") == "/opt/openjdk@17/something"


def test_uninstall_returns_false_when_installer_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _booted_manager(monkeypatch)
    m._installer.uninstall.return_value = False
    assert m.uninstall("21") is False


# ─── upgrade ────────────────────────────────────────────────────────────


def test_upgrade_specific_version(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_manager(monkeypatch)
    m._installer.upgrade.return_value = True
    assert m.upgrade("21") is True
    m._installer.upgrade.assert_called_with("21")


def test_upgrade_all_iterates_outdated(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_manager(monkeypatch)
    m._brew.outdated_java.return_value = [
        {"name": "openjdk@21"},
        {"name": "openjdk@17"},
        {"name": "git"},  # ignored (no @)
    ]
    m._installer.upgrade.return_value = True
    assert m.upgrade(None) is True
    calls = [c.args[0] for c in m._installer.upgrade.call_args_list]
    assert calls == ["21", "17"]


def test_upgrade_all_returns_false_when_any_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_manager(monkeypatch)
    m._brew.outdated_java.return_value = [{"name": "openjdk@21"}]
    m._installer.upgrade.return_value = False
    assert m.upgrade(None) is False


# ─── switch_active ──────────────────────────────────────────────────────


def test_switch_active_sets_java_home(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_manager(monkeypatch)
    m._installer.switch.return_value = True
    m._brew.prefix = "/opt/homebrew"
    monkeypatch.setattr(
        "shimkit.tools.java.manager.java_home_for",
        lambda prefix, v, is_macos: f"{prefix}/opt/openjdk@{v}/libexec/openjdk.jdk/Contents/Home",
    )
    assert m.switch_active("21") is True
    import os as _os

    assert "openjdk@21" in _os.environ.get("JAVA_HOME", "")
    _os.environ.pop("JAVA_HOME", None)


def test_switch_active_returns_false_when_switch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _booted_manager(monkeypatch)
    m._installer.switch.return_value = False
    assert m.switch_active("21") is False


# ─── list_installations / remove_oracle ─────────────────────────────────


def test_list_installations_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_manager(monkeypatch)
    expected = [JavaInstallation("Homebrew", "openjdk-21.jdk", "/x", True)]
    m._scanner.scan.return_value = expected
    assert m.list_installations() == expected


def test_remove_oracle_refuses_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_manager(monkeypatch)
    m._remover.available.return_value = False
    assert m.remove_oracle() is False


def test_remove_oracle_calls_remover(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_manager(monkeypatch)
    m._remover.available.return_value = True
    m._remover.remove.return_value = True
    assert m.remove_oracle() is True


# ─── check_java_updates ─────────────────────────────────────────────────


def test_check_java_updates_noop_when_brew_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _booted_manager(monkeypatch)
    m._brew.installed = False
    # Should return self even without spinning the prompt.
    assert m.check_java_updates() is m


def test_check_java_updates_noop_when_nothing_outdated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _booted_manager(monkeypatch)
    m._brew.installed = True
    m._brew.outdated_java.return_value = []

    class _SpinCtx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("shimkit.tools.java.manager.UI.spinner", lambda _msg: _SpinCtx())
    assert m.check_java_updates() is m


def test_check_java_updates_prompts_and_upgrades(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_manager(monkeypatch)
    m._brew.installed = True
    m._brew.outdated_java.return_value = [
        {
            "name": "openjdk@21",
            "installed_versions": ["21.0.1"],
            "current_version": "21.0.2",
        },
    ]

    class _SpinCtx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("shimkit.tools.java.manager.UI.spinner", lambda _msg: _SpinCtx())
    monkeypatch.setattr(
        "shimkit.tools.java.manager.Menu.confirm", lambda *a, **kw: True
    )
    m._installer.upgrade.return_value = True
    m.check_java_updates()
    m._installer.upgrade.assert_called_with("21")


# ─── check_self_update ──────────────────────────────────────────────────


def test_check_self_update_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_manager(monkeypatch)

    class FakeSU:
        check_on_startup = False

    class FakeCfg:
        self_update = FakeSU()

    monkeypatch.setattr("shimkit.tools.java.manager.get_config", lambda: FakeCfg())
    # Returns self without doing any spinner / network work.
    assert m.check_self_update() is m


def test_check_self_update_no_update_available(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _booted_manager(monkeypatch)

    class FakeSU:
        check_on_startup = True

    class FakeCfg:
        self_update = FakeSU()

    monkeypatch.setattr("shimkit.tools.java.manager.get_config", lambda: FakeCfg())

    class _Res:
        has_update = False
        method = None
        current = "0.10.0"
        latest = "0.10.0"

    class _SpinCtx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("shimkit.tools.java.manager.UI.spinner", lambda _msg: _SpinCtx())

    import shimkit.self_update as _su

    monkeypatch.setattr(_su, "check", lambda: _Res())
    assert m.check_self_update() is m


# ─── _menu_list (read-only, exercises banner/contextmanager path) ──────


def test_menu_list_prints_installations(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    m = _booted_manager(monkeypatch)
    m._scanner.scan.return_value = [
        JavaInstallation("Homebrew", "openjdk-21.jdk", "/opt/x", True),
        JavaInstallation("System", "java-17", "/usr/lib/jvm/java-17", False),
    ]
    m._scanner.active_version_string = "openjdk 21.0.1 2024-10-15\nLTS"
    monkeypatch.setattr("builtins.input", lambda _p: "")
    m._menu_list()
    out = capsys.readouterr().out
    assert "openjdk-21.jdk" in out
    assert "java-17" in out
    assert "Active" in out


def test_menu_list_handles_empty(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    m = _booted_manager(monkeypatch)
    m._scanner.scan.return_value = []
    m._scanner.active_version_string = "Not installed"

    def raise_eof(_p):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    m._menu_list()
    out = capsys.readouterr().out
    assert "No Java installations found" in out


# ─── _menu_remove_oracle (non-macOS path) ──────────────────────────────


def test_menu_remove_oracle_non_macos(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    m = _booted_manager(monkeypatch)
    m._remover.available.return_value = False
    m._menu_remove_oracle()
    out = capsys.readouterr().out
    assert "macOS only" in out


def test_menu_remove_oracle_no_oracle_found(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    m = _booted_manager(monkeypatch)
    m._remover.available.return_value = True
    m._scanner.scan.return_value = [
        JavaInstallation("Homebrew", "openjdk-21.jdk", "/x", True)
    ]
    m._menu_remove_oracle()
    out = capsys.readouterr().out
    assert "No Oracle" in out


# ─── _menu_uninstall (no installs) ─────────────────────────────────────


def test_menu_uninstall_no_installs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    m = _booted_manager(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = []
    m._menu_uninstall()
    out = capsys.readouterr().out
    assert "No Homebrew" in out


def test_menu_switch_no_installs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    m = _booted_manager(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = []
    m._menu_switch()
    out = capsys.readouterr().out
    assert "No Java installations" in out


def test_menu_switch_single_install(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    m = _booted_manager(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = ["21"]
    m._menu_switch()
    out = capsys.readouterr().out
    assert "Only one" in out


def test_menu_upgrade_no_installs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    m = _booted_manager(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = []
    m._menu_upgrade()
    out = capsys.readouterr().out
    assert "No Homebrew" in out


def test_menu_upgrade_all_up_to_date(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    m = _booted_manager(monkeypatch)
    m._scanner.homebrew_java_versions.return_value = ["21"]
    m._brew.outdated_java.return_value = []
    m._menu_upgrade()
    out = capsys.readouterr().out
    assert "up to date" in out


# ─── _print_banner ─────────────────────────────────────────────────────


def test_print_banner_outputs_content(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    m = _booted_manager(monkeypatch)
    m._print_banner("openjdk 21.0.1")
    out = capsys.readouterr().out
    assert "shimkit" in out
    assert "Java" in out
    assert "openjdk 21.0.1" in out
