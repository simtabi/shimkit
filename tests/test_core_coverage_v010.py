"""Coverage-tightening tests for core primitives.

Targets thin spots identified at the v0.9.0 baseline (~74%):
core/host_service, core/menu, core/command, core/systemd,
core/platform. These are pure-helper modules — no I/O once
mocked — so the tests are tight and the coverage gain is direct.
"""

from __future__ import annotations

import sys

import pytest

from shimkit.core import CommandResult
from shimkit.core import command as _cmd
from shimkit.core import host_service as _hs
from shimkit.core import menu as _menu
from shimkit.core import platform as _plat
from shimkit.core import systemd as _systemd

# ─── core/command ──────────────────────────────────────────────────────


def test_command_result_ok_property() -> None:
    assert CommandResult(0, "", "").ok
    assert not CommandResult(1, "", "").ok
    assert not CommandResult(-9, "", "").ok


def test_command_result_output_prefers_stdout() -> None:
    assert CommandResult(0, "hello\n", "err").output == "hello"


def test_command_result_output_falls_back_to_stderr() -> None:
    assert CommandResult(0, "", "boom").output == "boom"


def test_command_runner_run_string_splits_to_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen["cmd"] = cmd
        seen["kw"] = kw

        class R:
            returncode = 0
            stdout = "ok\n"
            stderr = ""

        return R()

    monkeypatch.setattr("shimkit.core.command.subprocess.run", fake_run)
    r = _cmd.CommandRunner.run("echo hi there")
    assert r.ok
    assert seen["cmd"] == ["echo", "hi", "there"]


def test_command_runner_run_shell_true_keeps_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen["cmd"] = cmd

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr("shimkit.core.command.subprocess.run", fake_run)
    _cmd.CommandRunner.run("echo $HOME", shell=True)
    assert seen["cmd"] == "echo $HOME"


def test_command_runner_run_called_process_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess as _sp

    def fake_run(*a, **kw):  # type: ignore[no-untyped-def]
        raise _sp.CalledProcessError(returncode=42, cmd=a, output="part", stderr="boom")

    monkeypatch.setattr("shimkit.core.command.subprocess.run", fake_run)
    r = _cmd.CommandRunner.run(["false"])
    assert r.returncode == 42
    assert r.stderr == "boom"


def test_command_runner_run_unexpected_exception_returns_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*a, **kw):  # type: ignore[no-untyped-def]
        raise OSError("permission denied")

    monkeypatch.setattr("shimkit.core.command.subprocess.run", fake_run)
    r = _cmd.CommandRunner.run(["ls"])
    assert r.returncode == 1
    assert "permission denied" in r.stderr


def test_sudo_prefix_root_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_cmd.os, "geteuid", lambda: 0)
    assert _cmd.sudo_prefix() == []


def test_sudo_prefix_non_root_with_sudo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_cmd.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(_cmd.shutil, "which", lambda _n: "/usr/bin/sudo")
    assert _cmd.sudo_prefix() == ["sudo"]


def test_sudo_prefix_non_root_no_sudo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_cmd.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(_cmd.shutil, "which", lambda _n: None)
    assert _cmd.sudo_prefix() == []


def test_is_root_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_cmd.os, "geteuid", lambda: 1000)
    assert not _cmd.is_root()


def test_is_root_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_cmd.os, "geteuid", lambda: 0)
    assert _cmd.is_root()


def test_has_sudo_cached_when_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_cmd, "is_root", lambda: True)
    assert _cmd.has_sudo_cached()


def test_has_sudo_cached_no_sudo_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_cmd, "is_root", lambda: False)
    monkeypatch.setattr(_cmd.shutil, "which", lambda _n: None)
    assert not _cmd.has_sudo_cached()


def test_has_sudo_cached_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_cmd, "is_root", lambda: False)
    monkeypatch.setattr(_cmd.shutil, "which", lambda _n: "/usr/bin/sudo")

    class R:
        returncode = 0

    monkeypatch.setattr("shimkit.core.command.subprocess.run", lambda *a, **kw: R())
    assert _cmd.has_sudo_cached()


def test_has_sudo_cached_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_cmd, "is_root", lambda: False)
    monkeypatch.setattr(_cmd.shutil, "which", lambda _n: "/usr/bin/sudo")
    import subprocess as _sp

    def raise_(*a, **kw):  # type: ignore[no-untyped-def]
        raise _sp.SubprocessError("timeout")

    monkeypatch.setattr("shimkit.core.command.subprocess.run", raise_)
    assert not _cmd.has_sudo_cached()


# ─── core/platform ─────────────────────────────────────────────────────


def test_platform_construction_defaults() -> None:
    p = _plat.Platform()
    assert p.system in ("Darwin", "Linux", "Windows")


def test_platform_macos_and_apple_silicon() -> None:
    p = _plat.Platform(system="Darwin", machine="arm64")
    assert p.is_macos
    assert p.is_apple_silicon
    assert not p.is_linux
    assert p.os_key == "macos"
    assert p.brew_prefix == "/opt/homebrew"
    assert "Apple Silicon" in p.description


def test_platform_macos_intel() -> None:
    p = _plat.Platform(system="Darwin", machine="x86_64")
    assert p.is_macos
    assert not p.is_apple_silicon
    assert p.brew_prefix == "/usr/local"


def test_platform_linux() -> None:
    p = _plat.Platform(system="Linux", machine="x86_64")
    assert p.is_linux
    assert p.os_key == "linux"
    assert p.is_supported
    assert p.jvm_base.as_posix() == "/usr/lib/jvm"


def test_platform_windows_unsupported() -> None:
    p = _plat.Platform(system="Windows", machine="x86_64")
    assert not p.is_supported
    assert p.os_key == "unknown"


def test_platform_is_wsl_reads_proc_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_wsl walks Path('/proc/version').read_text — patch the Path
    method to return a WSL-flavoured string."""
    p = _plat.Platform(system="Linux")
    original = _plat.Path.read_text

    def fake_read_text(self, *a, **kw):  # type: ignore[no-untyped-def]
        if str(self) == "/proc/version":
            return "Linux microsoft-standard-WSL2 build"
        return original(self, *a, **kw)

    monkeypatch.setattr(_plat.Path, "read_text", fake_read_text)
    assert p.is_wsl


def test_platform_is_wsl_oserror_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    p = _plat.Platform(system="Linux")

    def raise_oserror(self, *a, **kw):  # type: ignore[no-untyped-def]
        if str(self) == "/proc/version":
            raise OSError("not found")
        return ""

    monkeypatch.setattr(_plat.Path, "read_text", raise_oserror)
    assert not p.is_wsl


def test_platform_is_wsl_when_not_linux() -> None:
    p = _plat.Platform(system="Darwin", machine="arm64")
    assert not p.is_wsl


def test_platform_brew_prefix_linux_with_existing_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(
        _plat.Path,
        "exists",
        lambda self: str(self) == "/home/linuxbrew/.linuxbrew",
    )
    p = _plat.Platform(system="Linux", machine="x86_64")
    assert p.brew_prefix == "/home/linuxbrew/.linuxbrew"


def test_platform_description_with_container_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _plat.Path,
        "exists",
        lambda self: str(self) == "/.dockerenv",
    )
    p = _plat.Platform(system="Linux", machine="x86_64")
    assert "container" in p.description


# ─── core/menu ─────────────────────────────────────────────────────────


def test_fallback_menu_select_valid_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _p: "2")
    r = _menu.FallbackMenu().select("pick", ["a", "b", "c"])
    assert r.ask() == "b"


def test_fallback_menu_select_invalid_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _p: "99")
    r = _menu.FallbackMenu().select("pick", ["a", "b"])
    assert r.ask() is None


def test_fallback_menu_select_bad_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _p: "not-a-number")
    r = _menu.FallbackMenu().select("pick", ["a", "b"])
    assert r.ask() is None


def test_fallback_menu_select_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_eof(_p):  # type: ignore[no-untyped-def]
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    r = _menu.FallbackMenu().select("pick", ["a", "b"])
    assert r.ask() is None


def test_fallback_menu_confirm_default_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _p: "")
    r = _menu.FallbackMenu().confirm("ok?", default=True)
    assert r.ask() is True


def test_fallback_menu_confirm_default_no(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _p: "")
    r = _menu.FallbackMenu().confirm("ok?", default=False)
    assert r.ask() is False


def test_fallback_menu_confirm_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _p: "y")
    r = _menu.FallbackMenu().confirm("ok?", default=False)
    assert r.ask() is True


def test_fallback_menu_confirm_eof_returns_default(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_eof(_p):  # type: ignore[no-untyped-def]
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    r = _menu.FallbackMenu().confirm("ok?", default=True)
    assert r.ask() is True


def test_fallback_menu_checkbox_all_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _p: "")
    r = _menu.FallbackMenu().checkbox("pick", ["a", "b", "c"])
    assert r.ask() == ["a", "b", "c"]


def test_fallback_menu_checkbox_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _p: "1, 3")
    r = _menu.FallbackMenu().checkbox("pick", ["a", "b", "c"])
    assert r.ask() == ["a", "c"]


def test_fallback_menu_checkbox_bad_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _p: "garbage")
    r = _menu.FallbackMenu().checkbox("pick", ["a"])
    assert r.ask() == []


def test_menu_backend_falls_back_when_not_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert isinstance(_menu.Menu._backend(), _menu.FallbackMenu)


def test_menu_select_returns_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda _p: "1")
    assert _menu.Menu.select("Q", ["x", "y"]) == "x"


def test_menu_select_returns_none_on_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda _p: "99")
    assert _menu.Menu.select("Q", ["x", "y"]) is None


def test_menu_confirm_returns_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda _p: "y")
    assert _menu.Menu.confirm("ok?", default=False) is True


def test_menu_checkbox_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda _p: "")
    assert _menu.Menu.checkbox("Q", ["a", "b"]) == ["a", "b"]


def test_menu_prompt_for_change_yes_bypasses() -> None:
    assert _menu.Menu.prompt_for_change("Do thing", yes=True) is True


def test_menu_prompt_for_change_force_bypasses() -> None:
    assert _menu.Menu.prompt_for_change("Do thing", force=True) is True


def test_menu_prompt_for_change_no_input_refuses() -> None:
    assert _menu.Menu.prompt_for_change("Do thing", no_input=True) is False


def test_menu_prompt_for_change_not_tty_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert _menu.Menu.prompt_for_change("Do thing") is False


# ─── core/host_service ─────────────────────────────────────────────────


def test_host_service_detect_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    plat = _plat.Platform(system="Linux", machine="x86_64")
    impl = _hs.HostService.detect(plat)
    assert isinstance(impl, _hs.SystemdHost)


def test_host_service_detect_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    plat = _plat.Platform(system="Darwin", machine="arm64")
    impl = _hs.HostService.detect(plat)
    assert isinstance(impl, _hs.BrewServicesHost)


def test_host_service_detect_windows_none() -> None:
    plat = _plat.Platform(system="Windows", machine="x86_64")
    assert _hs.HostService.detect(plat) is None


def test_host_service_detect_default_uses_platform_detect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _plat.Platform,
        "detect",
        classmethod(lambda cls: _plat.Platform(system="Linux", machine="x86_64")),
    )
    assert isinstance(_hs.HostService.detect(), _hs.SystemdHost)


def test_systemd_host_state_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _systemd.Systemd,
        "state",
        staticmethod(
            lambda unit: _systemd.UnitState(name=unit, active=False, enabled=False, exists=False)
        ),
    )
    assert _hs.SystemdHost().state("mysql") == "missing"


def test_systemd_host_state_running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _systemd.Systemd,
        "state",
        staticmethod(
            lambda unit: _systemd.UnitState(name=unit, active=True, enabled=True, exists=True)
        ),
    )
    assert _hs.SystemdHost().state("mysql") == "running"


def test_systemd_host_state_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _systemd.Systemd,
        "state",
        staticmethod(
            lambda unit: _systemd.UnitState(name=unit, active=False, enabled=True, exists=True)
        ),
    )
    assert _hs.SystemdHost().state("mysql") == "stopped"


def test_systemd_host_start_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _systemd.Systemd,
        "start",
        staticmethod(lambda unit: CommandResult(0, "", "")),
    )
    monkeypatch.setattr(
        _systemd.Systemd,
        "state",
        staticmethod(
            lambda unit: _systemd.UnitState(name=unit, active=True, enabled=True, exists=True)
        ),
    )
    r = _hs.SystemdHost().start("mysql")
    assert r.ok
    assert r.state == "running"


def test_systemd_host_stop_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _systemd.Systemd,
        "stop",
        staticmethod(lambda unit: CommandResult(0, "", "")),
    )
    monkeypatch.setattr(
        _systemd.Systemd,
        "state",
        staticmethod(
            lambda unit: _systemd.UnitState(name=unit, active=False, enabled=True, exists=True)
        ),
    )
    r = _hs.SystemdHost().stop("mysql")
    assert r.ok
    assert r.state == "stopped"


def test_brew_host_state_running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _hs.CommandRunner,
        "run",
        staticmethod(
            lambda *a, **kw: CommandResult(
                0, "Name      Status    User    File\nmysql     started   you     ~/...\n", ""
            )
        ),
    )
    assert _hs.BrewServicesHost().state("mysql") == "running"


def test_brew_host_state_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _hs.CommandRunner,
        "run",
        staticmethod(
            lambda *a, **kw: CommandResult(0, "mysql     none      -       -\n", "")
        ),
    )
    assert _hs.BrewServicesHost().state("mysql") == "stopped"


def test_brew_host_state_missing_when_not_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _hs.CommandRunner,
        "run",
        staticmethod(lambda *a, **kw: CommandResult(0, "other-svc started\n", "")),
    )
    assert _hs.BrewServicesHost().state("mysql") == "missing"


def test_brew_host_state_missing_when_cmd_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _hs.CommandRunner,
        "run",
        staticmethod(lambda *a, **kw: CommandResult(127, "", "brew: not found")),
    )
    assert _hs.BrewServicesHost().state("mysql") == "missing"


def test_brew_host_start_invokes_brew_services(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        if cmd[:3] == ["brew", "services", "start"]:
            return CommandResult(0, "started", "")
        return CommandResult(0, "mysql     started\n", "")

    monkeypatch.setattr(_hs.CommandRunner, "run", staticmethod(fake_run))
    r = _hs.BrewServicesHost().start("mysql")
    assert r.ok
    assert ["brew", "services", "start", "mysql"] in seen


def test_brew_host_stop_invokes_brew_services(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        if cmd[:3] == ["brew", "services", "stop"]:
            return CommandResult(0, "stopped", "")
        return CommandResult(0, "mysql     stopped\n", "")

    monkeypatch.setattr(_hs.CommandRunner, "run", staticmethod(fake_run))
    r = _hs.BrewServicesHost().stop("mysql")
    assert r.ok
    assert ["brew", "services", "stop", "mysql"] in seen


# ─── core/systemd ──────────────────────────────────────────────────────


def test_systemd_is_active(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _systemd.CommandRunner,
        "run",
        staticmethod(lambda cmd, **kw: CommandResult(0, "", "")),
    )
    assert _systemd.Systemd.is_active("mysql")


def test_systemd_is_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _systemd.CommandRunner,
        "run",
        staticmethod(lambda cmd, **kw: CommandResult(0, "", "")),
    )
    assert _systemd.Systemd.is_enabled("mysql")


def test_systemd_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _systemd.CommandRunner,
        "run",
        staticmethod(lambda cmd, **kw: CommandResult(0, "", "")),
    )
    assert _systemd.Systemd.exists("mysql")


def test_systemd_state_returns_full_unit_state(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        # systemctl cat / is-active / is-enabled all return 0
        return CommandResult(0, "", "")

    monkeypatch.setattr(_systemd.CommandRunner, "run", staticmethod(fake_run))
    state = _systemd.Systemd.state("mysql")
    assert state.exists
    assert state.active
    assert state.enabled


def test_systemd_state_missing_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        if "cat" in cmd:
            return CommandResult(1, "", "no such unit")
        return CommandResult(0, "", "")

    monkeypatch.setattr(_systemd.CommandRunner, "run", staticmethod(fake_run))
    state = _systemd.Systemd.state("missing")
    assert not state.exists
    assert not state.active


def test_systemd_lifecycle_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(_systemd.CommandRunner, "run", staticmethod(fake_run))
    monkeypatch.setattr(_systemd, "sudo_prefix", lambda: ["sudo"])
    _systemd.Systemd.stop("mysql")
    _systemd.Systemd.start("mysql")
    _systemd.Systemd.restart("mysql")
    _systemd.Systemd.disable("mysql")
    _systemd.Systemd.daemon_reload()
    _systemd.Systemd.reload_or_restart("mysql")
    actions = [c[2] for c in seen]
    assert actions == ["stop", "start", "restart", "disable", "daemon-reload", "reload-or-restart"]


def test_systemd_journal_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(_systemd.CommandRunner, "run", staticmethod(fake_run))
    monkeypatch.setattr(_systemd, "sudo_prefix", lambda: [])
    _systemd.Systemd.journal("mysql", lines=200, follow=True)
    assert seen[0] == ["journalctl", "-u", "mysql", "-n", "200", "-f"]
