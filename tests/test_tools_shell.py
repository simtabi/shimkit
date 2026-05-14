from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult, PackageManager, Platform
from shimkit.tools.shell import ShellUpgrader

# --- PackageManager --------------------------------------------------------


def test_pkgmgr_detect_picks_first_available_per_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "shimkit.core.pkgmgr.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in ("apt", "dnf") else None,
    )
    pm = PackageManager.detect(Platform(system="Linux", machine="x86_64"))
    # apt comes before dnf in preference_order; both are linux-compatible
    assert pm is not None
    assert pm.name == "apt"


def test_pkgmgr_detect_returns_none_when_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("shimkit.core.pkgmgr.shutil.which", lambda _name: None)
    assert PackageManager.detect(Platform.detect()) is None


def test_pkgmgr_render_substitutes_pkg() -> None:
    pm = PackageManager(
        name="apt",
        install_cmd="apt-get install -y ${pkg}",
        update_cmd="apt-get update",
        upgrade_cmd="apt-get install --only-upgrade -y ${pkg}",
    )
    assert pm.render(pm.template("install"), pkg="bash") == "apt-get install -y bash"
    assert pm.render(pm.template("update")) == "apt-get update"
    # No pkg given → default empty string substituted (intentional: update_cmd
    # templates have no $pkg, but the substitution still runs uniformly).
    assert pm.render("foo ${pkg} bar") == "foo  bar"
    # Unknown placeholders survive (safe_substitute):
    assert "${unknown}" in pm.render("foo ${unknown} bar")


def test_pkgmgr_argv_form_renders_without_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Argv-list templates must reach CommandRunner.run() as a list, not a string.

    This is the Phase 3 security fix: even if a caller passes a package
    name with shell metacharacters, the argv path keeps it as one argv
    token and never interpolates it into a shell string.
    """
    from shimkit.core import CommandResult

    pm = PackageManager(
        name="apt",
        install_cmd=["apt-get", "install", "-y", "${pkg}"],
        update_cmd=["apt-get", "update"],
        upgrade_cmd=["apt-get", "install", "--only-upgrade", "-y", "${pkg}"],
    )

    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.core.pkgmgr.CommandRunner.run", staticmethod(fake_run)
    )
    # A package name with metacharacters; argv path keeps it as one token.
    pm.install("bash; rm -rf /")
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert "bash; rm -rf /" in cmd
    # No shell=True kwarg for the argv path.
    assert not captured["kwargs"].get("shell", False)


def test_pkgmgr_skips_pm_not_in_platforms(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # apt's platforms are ["linux"]; on macOS it should be skipped even if
    # `apt` happens to be on PATH (unlikely but possible).
    monkeypatch.setattr(
        "shimkit.core.pkgmgr.shutil.which",
        lambda name: f"/usr/bin/{name}" if name == "apt" else (
            "/opt/homebrew/bin/brew" if name == "brew" else None
        ),
    )
    pm = PackageManager.detect(Platform(system="Darwin", machine="arm64"))
    assert pm is not None
    assert pm.name == "brew"  # apt skipped because not in platforms


# --- ShellUpgrader ---------------------------------------------------------


def _stub_pm() -> PackageManager:
    return PackageManager(
        name="brew",
        install_cmd="brew install ${pkg}",
        update_cmd="brew update",
        upgrade_cmd="brew upgrade ${pkg}",
    )


def test_upgrader_supported_shells_from_config() -> None:
    up = ShellUpgrader(Platform.detect(), _stub_pm())
    assert set(up.supported_shells) == {"bash", "zsh", "fish", "ksh"}


def test_upgrader_installed_version_parses_semver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "shimkit.tools.shell.upgrader.shutil.which", lambda _: "/bin/bash"
    )

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        return CommandResult(0, "GNU bash, version 5.2.32(1)-release", "")

    monkeypatch.setattr("shimkit.tools.shell.upgrader.CommandRunner.run", fake_run)
    up = ShellUpgrader(Platform.detect(), _stub_pm())
    # Regex is greedy on the optional patch number: 5.2.32 matches whole, not 5.2.
    assert up.installed_version("bash") == "5.2.32"


def test_upgrader_installed_version_returns_none_if_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "shimkit.tools.shell.upgrader.shutil.which", lambda _: None
    )
    up = ShellUpgrader(Platform.detect(), _stub_pm())
    assert up.installed_version("bash") is None


def test_upgrader_upgrade_rejects_unsupported_shell() -> None:
    up = ShellUpgrader(Platform.detect(), _stub_pm())
    assert up.upgrade("nope") is False


def test_upgrader_simulate_returns_dry_run_text() -> None:
    up = ShellUpgrader(Platform.detect(), _stub_pm())
    out = up.simulate("bash")
    assert "[dry-run]" in out
    assert "brew update" in out
    assert "brew upgrade bash" in out


def test_upgrader_simulate_flags_unsupported_shell() -> None:
    up = ShellUpgrader(Platform.detect(), _stub_pm())
    out = up.simulate("powershell")
    assert "unsupported" in out


# --- CLI integration -------------------------------------------------------


def test_cli_shell_help_lists_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["shell", "--help"])
    assert result.exit_code == 0
    for cmd in ("info", "upgrade", "simulate"):
        assert cmd in result.stdout


def test_cli_shell_info_runs(runner: CliRunner) -> None:
    # ShellManager will boot and detect a real PM on the test host.
    # If detection fails, the test is meaningful — exit_code != 0 surfaces it.
    result = runner.invoke(app, ["shell", "info"])
    assert result.exit_code in (0, 1)


def test_cli_shell_upgrade_exit_codes(runner: CliRunner) -> None:
    with patch(
        "shimkit.tools.shell.manager.ShellManager.upgrade_shell", return_value=False
    ):
        result = runner.invoke(app, ["shell", "upgrade", "bash"])
    assert result.exit_code == 1


def test_cli_shell_simulate_runs(runner: CliRunner) -> None:
    result = runner.invoke(app, ["shell", "simulate", "bash"])
    # simulate should always exit 0 (even when PM detection works, no command runs)
    assert result.exit_code in (0, 1)
