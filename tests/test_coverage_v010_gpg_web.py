"""Coverage push for gpg/manager + web/nginx/manager.

GPG methods test the dispatch logic; nginx manager covers list,
apply (severe-token enforcement), and remove paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _patch_git_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """git-signing flow needs `gpg` for boot() + `git` for _check_git_or_warn.
    Provide both so we exercise the path validation, not the missing-binary check."""
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.shutil.which",
        lambda b: f"/usr/bin/{b}" if b in ("gpg", "git") else None,
    )
    _force_linux(monkeypatch)


def _patch_gpg_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.shutil.which",
        lambda b: f"/usr/bin/{b}" if b in ("gpg", "git") else None,
    )
    _force_linux(monkeypatch)


def _force_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )


def _bypass_gpg_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.core.version.preflight", lambda *a, **kw: None)


# ─── gpg keys_generate ────────────────────────────────────────────────


def test_gpg_keys_generate_unknown_key_type(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gpg_present(monkeypatch)
    _bypass_gpg_preflight(monkeypatch)
    result = runner.invoke(
        app,
        [
            "gpg",
            "keys",
            "generate",
            "User",
            "u@x.com",
            "--type",
            "magic",
            "--yes",
        ],
    )
    assert result.exit_code == 1


def test_gpg_keys_generate_dry_run(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gpg_present(monkeypatch)
    _bypass_gpg_preflight(monkeypatch)
    result = runner.invoke(
        app,
        [
            "gpg",
            "keys",
            "generate",
            "User",
            "u@x.com",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0


def test_gpg_keys_generate_runs_gpg(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gpg_present(monkeypatch)
    _bypass_gpg_preflight(monkeypatch)
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run", staticmethod(fake_run)
    )
    result = runner.invoke(
        app,
        [
            "gpg",
            "keys",
            "generate",
            "User",
            "u@x.com",
            "--yes",
        ],
    )
    assert result.exit_code == 0
    assert seen and seen[0][:2] == ["gpg", "--quick-gen-key"]


def test_gpg_keys_generate_failure_exits_1(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gpg_present(monkeypatch)
    _bypass_gpg_preflight(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(1, "", "boom")),
    )
    result = runner.invoke(
        app,
        [
            "gpg",
            "keys",
            "generate",
            "User",
            "u@x.com",
            "--yes",
        ],
    )
    assert result.exit_code == 1


# ─── gpg keys_export ──────────────────────────────────────────────────


def test_gpg_keys_export_to_stdout(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gpg_present(monkeypatch)
    _bypass_gpg_preflight(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(
            lambda *a, **kw: CommandResult(0, "-----BEGIN PGP PUBLIC KEY BLOCK-----\n", "")
        ),
    )
    result = runner.invoke(app, ["gpg", "keys", "export", "ABCDEF"])
    assert result.exit_code == 0
    assert "PUBLIC KEY BLOCK" in result.output


def test_gpg_keys_export_to_file(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_gpg_present(monkeypatch)
    _bypass_gpg_preflight(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(
            lambda *a, **kw: CommandResult(0, "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n", "")
        ),
    )
    out = tmp_path / "key.asc"
    result = runner.invoke(
        app, ["gpg", "keys", "export", "ABCDEF", "--dest", str(out)]
    )
    assert result.exit_code == 0
    assert out.read_text().startswith("-----BEGIN PGP")


def test_gpg_keys_export_failure(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gpg_present(monkeypatch)
    _bypass_gpg_preflight(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(2, "", "no such key")),
    )
    result = runner.invoke(app, ["gpg", "keys", "export", "DEADBEEF"])
    assert result.exit_code == 1


def test_gpg_keys_export_dry_run(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gpg_present(monkeypatch)
    _bypass_gpg_preflight(monkeypatch)
    result = runner.invoke(app, ["gpg", "keys", "export", "ABC", "--dry-run"])
    assert result.exit_code == 0


# ─── gpg git_signing_configure ───────────────────────────────────────


def test_gpg_git_signing_configure_unknown_scope(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_git_present(monkeypatch)
    _bypass_gpg_preflight(monkeypatch)
    result = runner.invoke(
        app, ["gpg", "git-signing", "configure", "ABC", "--scope", "weird", "--yes"]
    )
    assert result.exit_code == 1


def test_gpg_git_signing_configure_dry_run(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_git_present(monkeypatch)
    _bypass_gpg_preflight(monkeypatch)
    result = runner.invoke(
        app,
        [
            "gpg",
            "git-signing",
            "configure",
            "ABCDEF",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0


def test_gpg_git_signing_configure_runs_git_config(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_git_present(monkeypatch)
    _bypass_gpg_preflight(monkeypatch)
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run", staticmethod(fake_run)
    )
    result = runner.invoke(
        app,
        ["gpg", "git-signing", "configure", "ABCDEF", "--yes"],
    )
    assert result.exit_code == 0
    # Both git config calls (signingkey + commit.gpgsign) ran.
    assert len(seen) == 2


def test_gpg_git_signing_configure_failure(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_git_present(monkeypatch)
    _bypass_gpg_preflight(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(1, "", "config denied")),
    )
    result = runner.invoke(
        app,
        ["gpg", "git-signing", "configure", "X", "--yes"],
    )
    assert result.exit_code == 1


def test_gpg_git_signing_configure_no_git(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.shutil.which", lambda b: None
    )
    _bypass_gpg_preflight(monkeypatch)
    result = runner.invoke(
        app, ["gpg", "git-signing", "configure", "X", "--yes"]
    )
    assert result.exit_code == 69


# ─── gpg run() menu ───────────────────────────────────────────────────


def test_gpg_manager_run_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.gpg.manager import GpgManager

    mgr = GpgManager()
    called: list[str] = []
    monkeypatch.setattr(mgr, "keys_list", lambda: called.append("keys") or 0)
    monkeypatch.setattr(mgr, "agent_status", lambda: called.append("agent") or 0)
    monkeypatch.setattr(mgr, "git_signing_show", lambda: called.append("git") or 0)
    sequence = iter(
        ["List keys", "gpg-agent status", "Show git signing config", "Quit"]
    )
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.Menu.select",
        lambda *a, **kw: next(sequence),
    )
    mgr.run()
    assert called == ["keys", "agent", "git"]


def test_gpg_manager_run_quit_via_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.gpg.manager import GpgManager

    mgr = GpgManager()
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.Menu.select",
        lambda *a, **kw: None,
    )
    mgr.run()  # exits


# ─── web/nginx vhost remove (severe-token enforcement) ───────────────


def test_web_nginx_remove_missing_token(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remove requires the REMOVE-VHOST severe token."""
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.core.version.preflight", lambda *a, **kw: None)
    result = runner.invoke(app, ["web", "nginx", "vhost", "remove", "--name", "test"])
    assert result.exit_code != 0


def test_web_nginx_apply_missing_token(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Apply also requires the APPLY-VHOST token."""
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.core.version.preflight", lambda *a, **kw: None)
    src = tmp_path / "myapp.conf"
    src.write_text("server { }")
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "apply",
            "--name",
            "myapp",
            "--source",
            str(src),
        ],
    )
    assert result.exit_code != 0


def test_web_nginx_list_via_manager_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Direct manager call with empty sites-available dir."""
    from shimkit.tools.web.nginx.manager import WebNginxManager

    sites_avail = tmp_path / "sites-available"
    sites_enabled = tmp_path / "sites-enabled"
    sites_avail.mkdir()
    sites_enabled.mkdir()

    class _NginxCfg:
        sites_available_dir = str(sites_avail)
        sites_enabled_dir = str(sites_enabled)
        reload_cmd = ["nginx", "-s", "reload"]
        apply_severe_token = "APPLY-VHOST"
        remove_severe_token = "REMOVE-VHOST"
        default_php_version = "8.3"
        default_flavor = "static"
        managed_marker = "# managed-by: shimkit"

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
                        "web": type("Web", (), {"nginx": _NginxCfg()})(),
                    },
                )()
            },
        )(),
    )
    mgr = WebNginxManager()
    assert mgr.list_vhosts(json_out=False) == 0
