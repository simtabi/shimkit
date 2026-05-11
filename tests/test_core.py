from __future__ import annotations

import json
from pathlib import Path

import pytest

from shimkit.config import reset_cache
from shimkit.core import (
    UI,
    AskResult,
    CommandResult,
    CommandRunner,
    FallbackMenu,
    Platform,
    Shell,
    ShellConfigWriter,
    java_home_for,
    sudo_prefix,
)

# --- command ---------------------------------------------------------------


def test_command_result_ok_and_output() -> None:
    r = CommandResult(0, "  hello  ", "")
    assert r.ok is True
    assert r.output == "hello"

    bad = CommandResult(1, "", "  oops  ")
    assert bad.ok is False
    assert bad.output == "oops"  # falls back to stderr


def test_command_runner_runs_real_command() -> None:
    r = CommandRunner.run(["echo", "hi"])
    assert r.ok
    assert r.stdout.strip() == "hi"


def test_command_runner_swallows_failures() -> None:
    r = CommandRunner.run(["definitely-not-a-real-command-xyz"])
    assert not r.ok
    assert r.returncode != 0


def test_sudo_prefix_returns_list() -> None:
    p = sudo_prefix()
    # Either we're root → [], or sudo is on PATH → ["sudo"], or sudo is missing → [].
    assert p in ([], ["sudo"])


# --- platform --------------------------------------------------------------


def test_platform_detect_returns_instance() -> None:
    p = Platform.detect()
    assert isinstance(p, Platform)
    # Exactly one of macos/linux should be true on a supported host.
    assert p.is_supported is (p.is_macos or p.is_linux)


def test_platform_os_key_matches_system() -> None:
    p = Platform.detect()
    if p.is_macos:
        assert p.os_key == "macos"
    elif p.is_linux:
        assert p.os_key == "linux"


def test_platform_brew_prefix_is_string() -> None:
    p = Platform.detect()
    assert isinstance(p.brew_prefix, str)
    assert p.brew_prefix.startswith("/")


# --- shell -----------------------------------------------------------------


def test_shell_detect_reads_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/bin/zsh")
    p = Platform.detect()
    s = Shell.detect(p)
    assert s.name == "zsh"
    assert s.config_file.name == ".zshrc"


def test_shell_detect_unknown_falls_back_to_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/exotic-shell")
    p = Platform.detect()
    s = Shell.detect(p)
    assert s.config_file.name == ".profile"


def test_shell_uses_fallback_rc_when_primary_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    # Only the fallback exists on disk:
    (tmp_path / ".bashrc").touch()
    monkeypatch.setenv("SHELL", "/bin/bash")
    s = Shell.detect(Platform.detect())
    # Default config maps bash → .bash_profile (fallback .bashrc).
    # Primary missing, fallback present → fallback wins.
    assert s.config_file.name == ".bashrc"


def test_shell_prefers_primary_when_both_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".bash_profile").touch()
    (tmp_path / ".bashrc").touch()
    monkeypatch.setenv("SHELL", "/bin/bash")
    s = Shell.detect(Platform.detect())
    assert s.config_file.name == ".bash_profile"


def test_shell_uses_primary_when_neither_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")
    s = Shell.detect(Platform.detect())
    # Neither exists → return the primary so ensure_config_exists() creates it.
    assert s.config_file.name == ".bash_profile"


def test_shell_config_map_override_via_user_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "shimkit.json"
    override.write_text(
        json.dumps(
            {
                "tools": {
                    "shell": {
                        "supported_shells": ["bash", "zsh", "fish", "ksh"],
                        "config_map": {
                            "bash": {"rc_file": ".bashrc"},
                            "zsh": {"rc_file": ".zshrc"},
                            "sh": {"rc_file": ".profile"},
                            "fish": {"rc_file": ".config/fish/config.fish"},
                            "ksh": {"rc_file": ".kshrc"},
                        },
                    }
                }
            }
        )
    )
    monkeypatch.setenv("SHIMKIT_CONFIG", str(override))
    monkeypatch.setenv("SHELL", "/bin/bash")
    reset_cache()

    s = Shell.detect(Platform.detect())
    assert s.config_file.name == ".bashrc"  # config override took effect


def test_java_home_for_macos_vs_linux() -> None:
    mac = java_home_for("/opt/homebrew", "21", is_macos=True)
    assert mac.endswith("/openjdk@21/libexec/openjdk.jdk/Contents/Home")
    linux = java_home_for("/usr/local", "21", is_macos=False)
    assert linux == "/usr/local/opt/openjdk@21"


def test_shell_config_writer_is_idempotent(tmp_path: Path) -> None:
    rc = tmp_path / ".zshrc"
    rc.touch()
    writer = ShellConfigWriter(rc)

    writer.write_java_env("/opt/homebrew", "21", Platform.detect())
    first = rc.read_text()
    writer.write_java_env("/opt/homebrew", "21", Platform.detect())
    second = rc.read_text()

    assert first == second  # second write is a no-op
    assert first.count("# java-manager:openjdk@21") == 1


def test_shell_config_writer_remove_clears_block(tmp_path: Path) -> None:
    rc = tmp_path / ".zshrc"
    rc.touch()
    writer = ShellConfigWriter(rc)
    writer.write_java_env("/opt/homebrew", "21", Platform.detect())

    assert writer.remove_java_env("21") is True
    assert "openjdk@21" not in rc.read_text()
    assert writer.remove_java_env("21") is False  # already gone


# --- ui --------------------------------------------------------------------


def test_ui_emits_ansi_when_color_always(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    override = tmp_path / "shimkit.json"
    override.write_text(json.dumps({"ui": {"color": "always"}}))
    monkeypatch.setenv("SHIMKIT_CONFIG", str(override))
    reset_cache()

    UI.success("done")
    captured = capsys.readouterr()
    assert "\033[" in captured.out  # ANSI escape present


def test_ui_strips_ansi_when_color_never(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    reset_cache()

    UI.success("done")
    captured = capsys.readouterr()
    assert "\033[" not in captured.out
    assert "done" in captured.out


# --- menu ------------------------------------------------------------------


def test_ask_result_returns_wrapped_value() -> None:
    assert AskResult("hi").ask() == "hi"
    assert AskResult(None).ask() is None


def test_fallback_menu_select_with_valid_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "2")
    r = FallbackMenu().select("Pick:", ["a", "b", "c"])
    assert r.ask() == "b"


def test_fallback_menu_select_with_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", boom)
    r = FallbackMenu().select("Pick:", ["a", "b"])
    assert r.ask() is None


def test_fallback_menu_confirm_default_on_eof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", boom)
    assert FallbackMenu().confirm("Sure?", default=True).ask() is True
    assert FallbackMenu().confirm("Sure?", default=False).ask() is False
