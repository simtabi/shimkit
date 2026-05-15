"""Coverage-tightening tests for tool modules.

Targets the largest uncovered LOC at the v0.9.0 baseline:
java/scanner, java/brew, java/installer, shell/manager,
adguard/ports. All pure-helper logic — mocked at the OS boundary.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shimkit.core import CommandResult
from shimkit.core import platform as _plat
from shimkit.tools.adguard import ports as _ports
from shimkit.tools.java import brew as _brew
from shimkit.tools.java import installer as _installer
from shimkit.tools.java import scanner as _scanner
from shimkit.tools.java.models import JavaInstallation
from shimkit.tools.shell import manager as _shellmgr

# ─── java/brew ─────────────────────────────────────────────────────────


def test_brew_installed_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.tools.java.brew.shutil.which", lambda _: "/opt/homebrew/bin/brew")
    assert _brew.Brew(_plat.Platform(system="Darwin", machine="arm64")).installed


def test_brew_installed_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.tools.java.brew.shutil.which", lambda _: None)
    assert not _brew.Brew(_plat.Platform(system="Linux")).installed


def test_brew_prefix_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        return CommandResult(0, "/opt/homebrew", "")

    monkeypatch.setattr(_brew.CommandRunner, "run", staticmethod(fake_run))
    b = _brew.Brew(_plat.Platform(system="Darwin", machine="arm64"))
    assert b.prefix == "/opt/homebrew"
    # Second call uses cache (no extra subprocess).
    assert b.prefix == "/opt/homebrew"
    assert len(calls) == 1


def test_brew_prefix_falls_back_to_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _brew.CommandRunner, "run", staticmethod(lambda *a, **kw: CommandResult(1, "", ""))
    )
    b = _brew.Brew(_plat.Platform(system="Darwin", machine="arm64"))
    assert b.prefix == "/opt/homebrew"


def test_brew_update_install_reinstall_uninstall_upgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(_brew.CommandRunner, "run", staticmethod(fake_run))
    b = _brew.Brew(_plat.Platform(system="Darwin", machine="arm64"))
    b.update()
    b.install_pkg("openjdk@21")
    b.reinstall_pkg("openjdk@21")
    b.uninstall_pkg("openjdk@21")
    b.upgrade_pkg("openjdk@21")
    cmds = [c[1] for c in seen]
    assert cmds == ["update", "install", "reinstall", "uninstall", "upgrade"]


def test_brew_link_with_force(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(_brew.CommandRunner, "run", staticmethod(fake_run))
    b = _brew.Brew(_plat.Platform(system="Darwin", machine="arm64"))
    b.link("openjdk@21", force=True)
    assert seen[0] == ["brew", "link", "openjdk@21", "--force"]
    seen.clear()
    b.link("openjdk@21", force=False)
    assert seen[0] == ["brew", "link", "openjdk@21"]


def test_brew_outdated_java_returns_openjdk_formulae(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps(
        {
            "formulae": [
                {"name": "openjdk@21", "installed_versions": ["21.0.1"]},
                {"name": "git", "installed_versions": ["2.30"]},
                {"name": "openjdk@17", "installed_versions": ["17.0.5"]},
            ],
            "casks": [],
        }
    )
    monkeypatch.setattr(
        _brew.CommandRunner,
        "run",
        staticmethod(lambda *a, **kw: CommandResult(0, payload, "")),
    )
    b = _brew.Brew(_plat.Platform(system="Darwin", machine="arm64"))
    outdated = b.outdated_java()
    names = {f["name"] for f in outdated}
    assert names == {"openjdk@21", "openjdk@17"}


def test_brew_outdated_java_handles_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _brew.CommandRunner,
        "run",
        staticmethod(lambda *a, **kw: CommandResult(1, "", "boom")),
    )
    assert _brew.Brew(_plat.Platform(system="Darwin", machine="arm64")).outdated_java() == []


def test_brew_outdated_java_handles_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _brew.CommandRunner,
        "run",
        staticmethod(lambda *a, **kw: CommandResult(0, "not-json", "")),
    )
    assert _brew.Brew(_plat.Platform(system="Darwin", machine="arm64")).outdated_java() == []


def test_brew_install_self_rejects_non_https(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.config import reset_cache

    # Patch the config to return a non-HTTPS URL.
    class FakeBrewConfig:
        install_url = "http://insecure.example.com/install.sh"

    class FakeCfg:
        brew = FakeBrewConfig()

    monkeypatch.setattr("shimkit.tools.java.brew.get_config", lambda: FakeCfg())
    b = _brew.Brew(_plat.Platform(system="Darwin", machine="arm64"))
    assert b.install_self() is False
    reset_cache()


# ─── java/scanner ──────────────────────────────────────────────────────


def test_scanner_active_version_raw_strips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _scanner.CommandRunner,
        "run",
        staticmethod(
            lambda *a, **kw: CommandResult(0, "", "openjdk version \"21.0.1\" 2024\n")
        ),
    )
    s = _scanner.JavaScanner(_plat.Platform(system="Linux"), MagicMock())
    assert "21.0.1" in s._active_version_raw()


def test_scanner_active_version_raw_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _scanner.CommandRunner,
        "run",
        staticmethod(lambda *a, **kw: CommandResult(127, "", "command not found")),
    )
    s = _scanner.JavaScanner(_plat.Platform(system="Linux"), MagicMock())
    assert s._active_version_raw() == ""


def test_scanner_active_version_string_returns_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _scanner.CommandRunner,
        "run",
        staticmethod(lambda *a, **kw: CommandResult(127, "", "no such file")),
    )
    s = _scanner.JavaScanner(_plat.Platform(system="Linux"), MagicMock())
    assert s.active_version_string == "Not installed"


def test_scanner_scan_finds_jvm_dirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jvm_base = tmp_path / "JavaVirtualMachines"
    jvm_base.mkdir()
    (jvm_base / "openjdk-21.jdk").mkdir()
    (jvm_base / "jdk-22.jdk").mkdir()  # treated as Oracle

    class FakeJavaPaths:
        macos = [str(jvm_base)]
        linux: list[str] = []
        container: list[str] = []

    class FakeJava:
        scan_paths = FakeJavaPaths()

    class FakeTools:
        java = FakeJava()

    class FakeCfg:
        tools = FakeTools()

    monkeypatch.setattr("shimkit.tools.java.scanner.get_config", lambda: FakeCfg())
    monkeypatch.setattr(
        _scanner.CommandRunner,
        "run",
        staticmethod(lambda *a, **kw: CommandResult(0, "", "openjdk 21\n")),
    )
    monkeypatch.setenv("JAVA_HOME", "")  # no JAVA_HOME interference
    b = MagicMock()
    b.prefix = str(tmp_path / "noopt")
    s = _scanner.JavaScanner(_plat.Platform(system="Darwin", machine="arm64"), b)
    results = s.scan()
    versions = {r.version for r in results}
    assert "openjdk-21.jdk" in versions
    assert "jdk-22.jdk" in versions
    kinds = {r.kind for r in results}
    assert "Oracle" in kinds  # jdk-22.jdk is Oracle


def test_scanner_homebrew_java_versions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    opt = tmp_path / "opt"
    opt.mkdir()
    (opt / "openjdk@21").mkdir()
    (opt / "openjdk@17").mkdir()
    (opt / "openjdk@11").mkdir()
    (opt / "openjdk").mkdir()  # bare openjdk (no @) is skipped
    b = MagicMock()
    b.prefix = str(tmp_path)
    s = _scanner.JavaScanner(_plat.Platform(system="Darwin", machine="arm64"), b)
    versions = s.homebrew_java_versions()
    assert versions == ["21", "17", "11"]


def test_scanner_sdkman_and_java_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    sdkman = home / ".sdkman" / "candidates" / "java"
    sdkman.mkdir(parents=True)
    (sdkman / "21.0.1-tem").mkdir()
    java_home_target = tmp_path / "my-jdk"
    java_home_target.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("JAVA_HOME", str(java_home_target))

    class FakeJavaPaths:
        macos: list[str] = []
        linux: list[str] = []
        container: list[str] = []

    class FakeJava:
        scan_paths = FakeJavaPaths()

    class FakeTools:
        java = FakeJava()

    class FakeCfg:
        tools = FakeTools()

    monkeypatch.setattr("shimkit.tools.java.scanner.get_config", lambda: FakeCfg())
    monkeypatch.setattr(
        _scanner.CommandRunner,
        "run",
        staticmethod(lambda *a, **kw: CommandResult(0, "", "openjdk 21\n")),
    )
    s = _scanner.JavaScanner(
        _plat.Platform(system="Linux"), MagicMock(prefix=str(tmp_path / "no"))
    )
    results = s.scan()
    kinds = {r.kind for r in results}
    assert "SDKman" in kinds
    assert "JAVA_HOME" in kinds


# ─── java/installer ────────────────────────────────────────────────────


def test_installer_install_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    b = MagicMock()
    b.update.return_value = CommandResult(0, "", "")
    b.install_pkg.return_value = CommandResult(0, "", "")
    plat = _plat.Platform(system="Linux")
    sh = MagicMock()
    inst = _installer.JavaInstaller(plat, b, sh)

    class _SpinCtx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("shimkit.tools.java.installer.UI.spinner", lambda _msg: _SpinCtx())
    writer = MagicMock()
    monkeypatch.setattr(
        "shimkit.tools.java.installer.ShellConfigWriter.for_shell",
        lambda _s: writer,
    )
    assert inst.install("21") is True
    b.install_pkg.assert_called_with("openjdk@21")
    writer.write_java_env.assert_called_once()


def test_installer_install_fails_when_brew_install_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    b = MagicMock()
    b.update.return_value = CommandResult(0, "", "")
    b.install_pkg.return_value = CommandResult(1, "", "boom")
    inst = _installer.JavaInstaller(_plat.Platform(system="Linux"), b, MagicMock())

    class _SpinCtx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("shimkit.tools.java.installer.UI.spinner", lambda _msg: _SpinCtx())
    assert inst.install("21") is False


def test_installer_reinstall_success(monkeypatch: pytest.MonkeyPatch) -> None:
    b = MagicMock()
    b.reinstall_pkg.return_value = CommandResult(0, "", "")
    inst = _installer.JavaInstaller(_plat.Platform(system="Linux"), b, MagicMock())
    writer = MagicMock()
    monkeypatch.setattr(
        "shimkit.tools.java.installer.ShellConfigWriter.for_shell",
        lambda _s: writer,
    )
    assert inst.reinstall("21") is True


def test_installer_uninstall_success(monkeypatch: pytest.MonkeyPatch) -> None:
    b = MagicMock()
    b.uninstall_pkg.return_value = CommandResult(0, "", "")
    plat = _plat.Platform(system="Linux")  # _unlink no-op on Linux
    inst = _installer.JavaInstaller(plat, b, MagicMock())
    writer = MagicMock()
    monkeypatch.setattr(
        "shimkit.tools.java.installer.ShellConfigWriter.for_shell",
        lambda _s: writer,
    )
    assert inst.uninstall("21") is True
    writer.remove_java_env.assert_called_with("21")


def test_installer_upgrade_success() -> None:
    b = MagicMock()
    b.upgrade_pkg.return_value = CommandResult(0, "", "")
    inst = _installer.JavaInstaller(_plat.Platform(system="Linux"), b, MagicMock())
    assert inst.upgrade("21") is True


def test_installer_switch_uses_link() -> None:
    b = MagicMock()
    b.link.return_value = CommandResult(0, "", "")
    inst = _installer.JavaInstaller(_plat.Platform(system="Linux"), b, MagicMock())
    assert inst.switch("21") is True
    b.link.assert_called_with("openjdk@21", force=True)


def test_installer_verify_reads_returncode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _installer.CommandRunner,
        "run",
        staticmethod(lambda *a, **kw: CommandResult(0, "", "")),
    )
    inst = _installer.JavaInstaller(_plat.Platform(system="Linux"), MagicMock(), MagicMock())
    assert inst.verify() is True


def test_installer_reload_env_updates_os_environ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sh = MagicMock()
    sh.source.return_value = {"FOO": "bar"}
    inst = _installer.JavaInstaller(_plat.Platform(system="Linux"), MagicMock(), sh)
    assert inst.reload_env() is True
    import os as _os

    assert _os.environ.get("FOO") == "bar"
    _os.environ.pop("FOO", None)


def test_installer_reload_env_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    sh = MagicMock()
    sh.source.return_value = {}
    inst = _installer.JavaInstaller(_plat.Platform(system="Linux"), MagicMock(), sh)
    assert inst.reload_env() is False


def test_installer_link_skips_on_linux() -> None:
    """_link is a no-op on Linux (the JVM symlinks live under
    /Library/Java/JavaVirtualMachines on macOS only)."""
    inst = _installer.JavaInstaller(_plat.Platform(system="Linux"), MagicMock(), MagicMock())
    inst._link("21")  # no exception, no shell-outs


def test_installer_unlink_skips_on_linux() -> None:
    inst = _installer.JavaInstaller(_plat.Platform(system="Linux"), MagicMock(), MagicMock())
    inst._unlink("21")


# ─── shell/manager ─────────────────────────────────────────────────────


def test_shell_manager_boot_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _plat.Platform,
        "detect",
        classmethod(lambda cls: _plat.Platform(system="Windows")),
    )
    with pytest.raises(SystemExit) as exc:
        _shellmgr.ShellManager.create().boot()
    assert exc.value.code == 1


def test_shell_manager_boot_no_pkgmgr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _plat.Platform,
        "detect",
        classmethod(lambda cls: _plat.Platform(system="Linux")),
    )
    monkeypatch.setattr(_shellmgr.PackageManager, "detect", classmethod(lambda cls, _: None))
    with pytest.raises(SystemExit) as exc:
        _shellmgr.ShellManager.create().boot()
    assert exc.value.code == 1


def test_shell_manager_info_outputs_shells(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        _plat.Platform,
        "detect",
        classmethod(lambda cls: _plat.Platform(system="Linux", machine="x86_64")),
    )

    class FakePM:
        name = "apt"

    monkeypatch.setattr(
        _shellmgr.PackageManager, "detect", classmethod(lambda cls, _: FakePM())
    )
    m = _shellmgr.ShellManager.create().boot()
    upgrader = MagicMock()
    upgrader.supported_shells = ["bash", "zsh"]
    upgrader.installed_version = lambda name: "5.1" if name == "bash" else None
    m._upgrader = upgrader  # type: ignore[assignment]

    class FakeShell:
        name = "bash"
        description = "bash 5.1"

    monkeypatch.setattr("shimkit.tools.shell.manager.Shell.detect", lambda _p: FakeShell())
    m.info()
    out = capsys.readouterr().out
    assert "bash" in out
    assert "zsh" in out
    assert "5.1" in out
    assert "not installed" in out


def test_shell_manager_upgrade_unknown_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _plat.Platform,
        "detect",
        classmethod(lambda cls: _plat.Platform(system="Linux")),
    )

    class FakePM:
        name = "apt"

    monkeypatch.setattr(
        _shellmgr.PackageManager, "detect", classmethod(lambda cls, _: FakePM())
    )
    m = _shellmgr.ShellManager.create().boot()
    upgrader = MagicMock()
    upgrader.supported_shells = ["bash", "zsh"]
    m._upgrader = upgrader  # type: ignore[assignment]
    assert m.upgrade_shell("tcsh") is False


def test_shell_manager_upgrade_force_skips_active_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _plat.Platform,
        "detect",
        classmethod(lambda cls: _plat.Platform(system="Linux")),
    )

    class FakePM:
        name = "apt"

    monkeypatch.setattr(
        _shellmgr.PackageManager, "detect", classmethod(lambda cls, _: FakePM())
    )

    class FakeShell:
        name = "bash"

    monkeypatch.setattr("shimkit.tools.shell.manager.Shell.detect", lambda _p: FakeShell())
    m = _shellmgr.ShellManager.create().boot()
    upgrader = MagicMock()
    upgrader.supported_shells = ["bash"]
    upgrader.upgrade.return_value = True
    m._upgrader = upgrader  # type: ignore[assignment]
    # force=True bypasses the active-shell prompt
    assert m.upgrade_shell("bash", force=True) is True
    upgrader.upgrade.assert_called_once_with("bash")


def test_shell_manager_simulate_outputs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        _plat.Platform,
        "detect",
        classmethod(lambda cls: _plat.Platform(system="Linux")),
    )

    class FakePM:
        name = "apt"

    monkeypatch.setattr(
        _shellmgr.PackageManager, "detect", classmethod(lambda cls, _: FakePM())
    )
    m = _shellmgr.ShellManager.create().boot()
    upgrader = MagicMock()
    upgrader.simulate.return_value = "apt-get install bash"
    m._upgrader = upgrader  # type: ignore[assignment]
    m.simulate("bash")
    out = capsys.readouterr().out
    assert "apt-get install bash" in out


# ─── adguard/ports ─────────────────────────────────────────────────────


def test_pid_to_unit_returns_none_when_cgroup_missing(tmp_path: Path) -> None:
    assert _ports._pid_to_unit(99999, proc_root=tmp_path) is None


def test_pid_to_unit_prefers_unified_hierarchy(tmp_path: Path) -> None:
    pid_dir = tmp_path / "42"
    pid_dir.mkdir()
    cgroup = pid_dir / "cgroup"
    cgroup.write_text(
        # cgroup v1 lines + cgroup v2 line — we prefer the latter.
        "12:cpu:/system.slice/legacy.scope\n"
        "0::/system.slice/example.service\n",
        encoding="utf-8",
    )
    assert _ports._pid_to_unit(42, proc_root=tmp_path) == "example.service"


def test_pid_to_unit_falls_back_to_legacy(tmp_path: Path) -> None:
    pid_dir = tmp_path / "42"
    pid_dir.mkdir()
    cgroup = pid_dir / "cgroup"
    cgroup.write_text(
        "12:cpu:/system.slice/example.service\n"
        "11:memory:/system.slice/example.service\n",
        encoding="utf-8",
    )
    assert _ports._pid_to_unit(42, proc_root=tmp_path) == "example.service"


def test_pid_to_unit_returns_none_for_orphan_pid(tmp_path: Path) -> None:
    pid_dir = tmp_path / "42"
    pid_dir.mkdir()
    (pid_dir / "cgroup").write_text("12:cpu:/\n0::/\n", encoding="utf-8")
    assert _ports._pid_to_unit(42, proc_root=tmp_path) is None


def test_is_agh_process_exact_and_truncated() -> None:
    """Linux kernel truncates `comm` to 15 chars; "AdGuardHome" is 11
    chars and still fits, longer variants (e.g. "AdGuardHomeFul" for
    a hypothetical 14-char binary) start with it. Anything shorter
    than "AdGuardHome" fails the prefix check."""
    assert _ports.is_agh_process("AdGuardHome")
    assert _ports.is_agh_process("AdGuardHomeFul")
    assert not _ports.is_agh_process("AdGuardHom")
    assert not _ports.is_agh_process("nginx")


def test_owners_of_rejects_unknown_proto() -> None:
    # We can't easily mock psutil here; just assert the protocol gate.
    pytest.importorskip("psutil")
    assert _ports.owners_of(53, "icmp") == []


def test_owners_of_empty_when_psutil_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):  # type: ignore[no-untyped-def]
        if name == "psutil":
            raise ImportError("not installed")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert _ports.owners_of(53, "tcp") == []


# ─── java/models (small final dust-up) ─────────────────────────────────


def test_java_installation_is_dataclass_like() -> None:
    j = JavaInstallation(kind="Homebrew", version="openjdk-21.jdk", path="/x", active=True)
    assert j.kind == "Homebrew"
    assert j.active
    assert j.version == "openjdk-21.jdk"
