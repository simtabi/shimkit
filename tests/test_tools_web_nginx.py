"""Tests for ``shimkit web nginx``.

Templates are pure-string-in/-out and tested directly. Manager
operations that would touch the host (`apply`, `remove`, reload)
are tested with `sudo install` + `ln -sfn` + `nginx -s reload`
mocked at the CommandRunner boundary, using tmp dirs in place of
`/etc/nginx/`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult
from shimkit.tools.web.nginx import templates

# ─── templates ──────────────────────────────────────────────────────────


def test_render_static_starts_with_managed_marker() -> None:
    out = templates.render(
        "static",
        name="docs",
        domain="docs.local",
        root="/srv/docs",
        php_version="8.3",
        managed_marker="# managed-by: shimkit",
    )
    assert out.startswith("# managed-by: shimkit")
    assert "server_name docs.local;" in out
    assert "root /srv/docs;" in out


def test_render_php_includes_fastcgi_socket() -> None:
    out = templates.render(
        "php",
        name="myapp",
        domain="myapp.local",
        root="/srv/myapp",
        php_version="8.3",
        managed_marker="# managed-by: shimkit",
    )
    assert "/run/php/php8.3-fpm.sock" in out
    assert "location ~ \\.php$" in out
    assert "/index.php?$args" in out


def test_render_laravel_appends_public_to_root() -> None:
    out = templates.render(
        "laravel",
        name="lara",
        domain="lara.local",
        root="/srv/lara",
        php_version="8.3",
        managed_marker="# managed-by: shimkit",
    )
    assert "root /srv/lara/public;" in out
    assert "/run/php/php8.3-fpm.sock" in out


def test_render_php_version_is_substituted() -> None:
    out = templates.render(
        "php",
        name="x",
        domain="x.local",
        root="/srv/x",
        php_version="8.1",
        managed_marker="# managed-by: shimkit",
    )
    assert "/run/php/php8.1-fpm.sock" in out
    assert "8.3" not in out


def test_render_security_headers_present_on_every_flavor() -> None:
    for flavor in templates.FLAVORS:
        out = templates.render(
            flavor,
            name="x",
            domain="x.local",
            root="/srv/x",
            php_version="8.3",
            managed_marker="# managed-by: shimkit",
        )
        for header in (
            "X-Frame-Options",
            "X-Content-Type-Options",
            "X-XSS-Protection",
            "Referrer-Policy",
            "Permissions-Policy",
            "server_tokens off;",
        ):
            assert header in out, f"{header!r} missing from {flavor}"


def test_render_unknown_flavor_raises() -> None:
    with pytest.raises(ValueError, match="Unknown flavor"):
        templates.render(
            "node",
            name="x",
            domain="x.local",
            root="/srv/x",
            php_version="8.3",
            managed_marker="# managed-by: shimkit",
        )


# ─── generate ───────────────────────────────────────────────────────────


def test_generate_stdout(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "generate",
            "--name",
            "docs",
            "--domain",
            "docs.local",
            "--root",
            "/srv/docs",
            "--flavor",
            "static",
        ],
    )
    assert result.exit_code == 0
    assert "server_name docs.local;" in result.stdout


def test_generate_to_file(runner: CliRunner, tmp_path: Path) -> None:
    out = tmp_path / "vhost.conf"
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "generate",
            "--name",
            "docs",
            "--domain",
            "docs.local",
            "--root",
            "/srv/docs",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0
    body = out.read_text()
    assert "managed-by: shimkit" in body
    assert "server_name docs.local;" in body


def test_generate_json_includes_body(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "generate",
            "--name",
            "docs",
            "--domain",
            "docs.local",
            "--root",
            "/srv/docs",
            "--json",
        ],
    )
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert "server_name docs.local;" in doc["data"]["body"]


def test_generate_unknown_flavor_errors(runner: CliRunner) -> None:
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
            "x.local",
            "--root",
            "/srv/x",
            "--flavor",
            "vue",
        ],
    )
    assert result.exit_code == 1
    assert "Unknown flavor" in result.stdout


# ─── apply (SEVERE) ─────────────────────────────────────────────────────


def _stub_command_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    install_succeeds: bool = True,
    symlink_succeeds: bool = True,
    reload_succeeds: bool = True,
    rm_succeeds: bool = True,
) -> list[list[str]]:
    """Stub CommandRunner.run; simulate sudo install, ln -sfn, etc.

    Returns the captured list of every argv that flowed through.
    """
    captured: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        cmd_l = list(cmd)
        captured.append(cmd_l)
        if "install" in cmd_l:
            if install_succeeds:
                src, dst = cmd_l[-2], cmd_l[-1]
                shutil.copy(src, dst)
            return CommandResult(0 if install_succeeds else 1, "", "")
        if "ln" in cmd_l:
            if symlink_succeeds:
                target, link = cmd_l[-2], cmd_l[-1]
                Path(link).parent.mkdir(parents=True, exist_ok=True)
                # Python's Path.symlink_to doesn't replace; rm first.
                Path(link).unlink(missing_ok=True)
                Path(link).symlink_to(target)
            return CommandResult(0 if symlink_succeeds else 1, "", "")
        if "rm" in cmd_l:
            if rm_succeeds:
                p = Path(cmd_l[-1])
                if p.exists() or p.is_symlink():
                    p.unlink()
            return CommandResult(0 if rm_succeeds else 1, "", "")
        if cmd_l[-2:] == ["-s", "reload"]:
            return CommandResult(0 if reload_succeeds else 1, "", "")
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.web.nginx.manager.CommandRunner.run",
        staticmethod(fake_run),
    )
    monkeypatch.setattr("shimkit.tools.web.nginx.manager.sudo_prefix", lambda: [])
    monkeypatch.setattr(
        "shimkit.tools.web.nginx.manager.shutil.which",
        lambda b: f"/usr/sbin/{b}",
    )
    return captured


def _redirect_nginx_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    avail = tmp_path / "sites-available"
    enabled = tmp_path / "sites-enabled"
    avail.mkdir()
    enabled.mkdir()
    cfg_override = tmp_path / "shimkit.json"
    cfg_override.write_text(
        json.dumps(
            {
                "tools": {
                    "web": {
                        "nginx": {
                            "sites_available_dir": str(avail),
                            "sites_enabled_dir": str(enabled),
                        }
                    }
                }
            }
        )
    )
    monkeypatch.setenv("SHIMKIT_CONFIG", str(cfg_override))
    from shimkit.config import reset_cache

    reset_cache()
    return avail, enabled


def test_apply_refuses_without_severe_token(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_command_runner(monkeypatch)
    _redirect_nginx_dirs(monkeypatch, tmp_path)
    src = tmp_path / "vhost.conf"
    src.write_text("# managed-by: shimkit\nserver { ... }\n")
    result = runner.invoke(
        app,
        ["web", "nginx", "vhost", "apply", "--name", "docs", "--source", str(src)],
    )
    assert result.exit_code == 1
    assert "APPLY-VHOST" in result.stdout


def test_apply_refuses_source_without_managed_marker(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_command_runner(monkeypatch)
    _redirect_nginx_dirs(monkeypatch, tmp_path)
    src = tmp_path / "external.conf"
    src.write_text("# something else\nserver { ... }\n")
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "apply",
            "--name",
            "docs",
            "--source",
            str(src),
            "--confirm",
            "APPLY-VHOST",
        ],
    )
    assert result.exit_code == 1
    assert "managed marker" in result.stdout


def test_apply_writes_avail_and_enabled_then_reloads(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _stub_command_runner(monkeypatch)
    avail, enabled = _redirect_nginx_dirs(monkeypatch, tmp_path)
    src = tmp_path / "vhost.conf"
    src.write_text("# managed-by: shimkit\nserver { listen 80; }\n")
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "apply",
            "--name",
            "docs",
            "--source",
            str(src),
            "--confirm",
            "APPLY-VHOST",
        ],
    )
    assert result.exit_code == 0
    assert (avail / "docs").is_file()
    assert (enabled / "docs").is_symlink()
    # Reload was invoked.
    assert any(cmd[-2:] == ["-s", "reload"] for cmd in captured)


def test_apply_refuses_to_overwrite_external_vhost(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_command_runner(monkeypatch)
    avail, _enabled = _redirect_nginx_dirs(monkeypatch, tmp_path)
    # Pre-existing non-shimkit vhost at the target path.
    (avail / "docs").write_text("# external admin\nserver { ... }\n")
    src = tmp_path / "vhost.conf"
    src.write_text("# managed-by: shimkit\nserver { ... }\n")
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "apply",
            "--name",
            "docs",
            "--source",
            str(src),
            "--confirm",
            "APPLY-VHOST",
        ],
    )
    assert result.exit_code == 1
    assert "doesn't have the managed marker" in result.stdout


def test_apply_dry_run_does_nothing(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _stub_command_runner(monkeypatch)
    avail, _enabled = _redirect_nginx_dirs(monkeypatch, tmp_path)
    src = tmp_path / "vhost.conf"
    src.write_text("# managed-by: shimkit\nserver { ... }\n")
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "apply",
            "--name",
            "docs",
            "--source",
            str(src),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert not (avail / "docs").exists()
    assert captured == []


# ─── remove (SEVERE) ────────────────────────────────────────────────────


def test_remove_refuses_without_severe_token(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_command_runner(monkeypatch)
    _redirect_nginx_dirs(monkeypatch, tmp_path)
    result = runner.invoke(app, ["web", "nginx", "vhost", "remove", "--name", "docs"])
    assert result.exit_code == 1


def test_remove_unlinks_and_reloads(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _stub_command_runner(monkeypatch)
    avail, enabled = _redirect_nginx_dirs(monkeypatch, tmp_path)
    (avail / "docs").write_text("# managed-by: shimkit\nserver { ... }\n")
    (enabled / "docs").symlink_to(avail / "docs")
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "remove",
            "--name",
            "docs",
            "--confirm",
            "REMOVE-VHOST",
        ],
    )
    assert result.exit_code == 0
    assert not (avail / "docs").exists()
    assert not (enabled / "docs").exists()
    assert any(cmd[-2:] == ["-s", "reload"] for cmd in captured)


def test_remove_refuses_external_vhost(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_command_runner(monkeypatch)
    avail, _enabled = _redirect_nginx_dirs(monkeypatch, tmp_path)
    (avail / "docs").write_text("# external\nserver { ... }\n")
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "remove",
            "--name",
            "docs",
            "--confirm",
            "REMOVE-VHOST",
        ],
    )
    assert result.exit_code == 1
    assert "no managed marker" in result.stdout


def test_remove_missing_is_noop(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_command_runner(monkeypatch)
    _redirect_nginx_dirs(monkeypatch, tmp_path)
    result = runner.invoke(
        app,
        [
            "web",
            "nginx",
            "vhost",
            "remove",
            "--name",
            "absent",
            "--confirm",
            "REMOVE-VHOST",
        ],
    )
    assert result.exit_code == 0
    assert "nothing to remove" in result.stdout


# ─── list ───────────────────────────────────────────────────────────────


def test_list_empty(runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _redirect_nginx_dirs(monkeypatch, tmp_path)
    result = runner.invoke(app, ["web", "nginx", "vhost", "list", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["entries"] == []


def test_list_flags_managed_vs_external(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    avail, enabled = _redirect_nginx_dirs(monkeypatch, tmp_path)
    managed = avail / "docs"
    managed.write_text("# managed-by: shimkit\nserver { ... }\n")
    (enabled / "docs").symlink_to(managed)

    external = avail / "ops"
    external.write_text("# something else\nserver { ... }\n")
    (enabled / "ops").symlink_to(external)

    result = runner.invoke(app, ["web", "nginx", "vhost", "list", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    by_name = {e["name"]: e for e in doc["data"]["entries"]}
    assert by_name["docs"]["managed"] is True
    assert by_name["ops"]["managed"] is False
