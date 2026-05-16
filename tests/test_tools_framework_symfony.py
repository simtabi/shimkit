"""Tests for ``shimkit framework symfony``.

Mirrors the Laravel test shape: platform gating, perms with group
detection, env scaffold, cache-clear delegation, console host vs
container paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult
from shimkit.core.platform import Platform
from shimkit.tools.framework.symfony.manager import SymfonyManager

# ─── helpers ────────────────────────────────────────────────────────────


def _force_unix(monkeypatch: pytest.MonkeyPatch, system: str = "Linux") -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system=system, machine="x86_64")),
    )


def _stub_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    group_exists: bool = True,
    php_present: bool = True,
) -> list[list[str]]:
    """Capture every CommandRunner.run call. Pretend `getent group`
    resolves; pretend `php -v` returns a recognised version.
    """
    calls: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        cmd_l = list(cmd) if not isinstance(cmd, str) else cmd.split()
        calls.append(cmd_l)
        if cmd_l[:2] == ["getent", "group"]:
            return (
                CommandResult(0, f"{cmd_l[2]}:x:33:\n", "")
                if group_exists
                else CommandResult(2, "", "")
            )
        if cmd_l[:2] == ["dscl", "."]:
            return CommandResult(0 if group_exists else 1, "", "")
        if cmd_l[:2] == ["php", "-v"]:
            return (
                CommandResult(0, "PHP 8.3.1 (cli)\n", "")
                if php_present
                else CommandResult(127, "", "php: not found")
            )
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.framework.symfony.manager.CommandRunner.run",
        staticmethod(fake_run),
    )
    monkeypatch.setattr(
        "shimkit.tools.framework.symfony.manager.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in ("getent", "php") else None,
    )
    return calls


def _make_symfony_skeleton(root: Path) -> None:
    """Build a minimal directory that passes our 'looks-like-Symfony' check."""
    (root / "var").mkdir(parents=True)
    bin_dir = root / "bin"
    bin_dir.mkdir()
    (bin_dir / "console").write_text("#!/usr/bin/env php\n<?php\n", encoding="utf-8")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── platform gating ────────────────────────────────────────────────────


def test_boot_exits_69_on_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Windows", machine="x86_64")),
    )
    with pytest.raises(SystemExit) as exc:
        SymfonyManager.create().boot()
    assert exc.value.code == 69


def test_boot_accepts_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_unix(monkeypatch)
    mgr = SymfonyManager.create().boot()
    assert mgr._platform is not None
    assert mgr._platform.is_linux


def test_boot_accepts_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_unix(monkeypatch, system="Darwin")
    mgr = SymfonyManager.create().boot()
    assert mgr._platform.is_macos


# ─── perms ──────────────────────────────────────────────────────────────


def test_perms_rejects_missing_path(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    nonexistent = tmp_path / "nope"
    result = runner.invoke(
        app, ["framework", "symfony", "perms", "--yes", str(nonexistent)]
    )
    assert result.exit_code == 1


def test_perms_dry_run_lists_commands(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    _make_symfony_skeleton(tmp_path)
    result = runner.invoke(
        app, ["framework", "symfony", "perms", "--dry-run", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "find" in result.stdout
    assert "chmod" in result.stdout


def test_perms_targets_var_dir(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Symfony's writable tree is var/, not Laravel's storage."""
    _force_unix(monkeypatch)
    _make_symfony_skeleton(tmp_path)
    calls = _stub_runner(monkeypatch, group_exists=True)
    result = runner.invoke(
        app, ["framework", "symfony", "perms", "--yes", str(tmp_path)]
    )
    assert result.exit_code == 0, result.stdout
    flat = [" ".join(c) for c in calls]
    # chgrp + chmod -R ug+rwx land on the var/ dir.
    assert any("chgrp -R www-data" in c and c.endswith("/var") for c in flat)
    assert any("chmod -R ug+rwx" in c and c.endswith("/var") for c in flat)


def test_perms_skips_chgrp_when_group_missing(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_symfony_skeleton(tmp_path)
    calls = _stub_runner(monkeypatch, group_exists=False)
    result = runner.invoke(
        app, ["framework", "symfony", "perms", "--yes", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert not any(c and c[0] == "chgrp" for c in calls)


def test_perms_group_flag_overrides(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_symfony_skeleton(tmp_path)
    calls = _stub_runner(monkeypatch, group_exists=True)
    result = runner.invoke(
        app,
        ["framework", "symfony", "perms", "--yes", "--group", "staff", str(tmp_path)],
    )
    assert result.exit_code == 0
    flat = [" ".join(c) for c in calls]
    assert any("chgrp -R staff" in c for c in flat)


def test_perms_json_failed_steps(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_symfony_skeleton(tmp_path)

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        cmd_l = list(cmd) if not isinstance(cmd, str) else cmd.split()
        if cmd_l[:2] == ["getent", "group"]:
            return CommandResult(0, "www-data:x:33:\n", "")
        if cmd_l[0] == "chgrp":
            return CommandResult(1, "", "operation not permitted")
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.framework.symfony.manager.CommandRunner.run",
        staticmethod(fake_run),
    )
    monkeypatch.setattr(
        "shimkit.tools.framework.symfony.manager.shutil.which",
        lambda name: "/usr/bin/getent" if name == "getent" else None,
    )
    result = runner.invoke(
        app, ["framework", "symfony", "perms", "--yes", "--json", str(tmp_path)]
    )
    assert result.exit_code == 1
    doc = json.loads(result.output)
    assert doc["data"]["failed"]
    assert any("chgrp" in line for line in doc["data"]["failed"])


# ─── env scaffold ──────────────────────────────────────────────────────


def test_env_refuses_overwrite(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    (tmp_path / ".env.local").write_text("existing\n")
    result = runner.invoke(
        app, ["framework", "symfony", "env", "--yes", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "refusing to overwrite" in result.output.lower()


def test_env_writes_app_secret_hex(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    result = runner.invoke(
        app, ["framework", "symfony", "env", "--yes", str(tmp_path)]
    )
    assert result.exit_code == 0, result.stdout
    body = (tmp_path / ".env.local").read_text()
    assert "APP_SECRET=" in body
    # APP_SECRET is hex(32 bytes) = 64 hex chars.
    line = next(ln for ln in body.splitlines() if ln.startswith("APP_SECRET="))
    secret = line.split("=", 1)[1]
    assert len(secret) == 64
    assert all(c in "0123456789abcdef" for c in secret)


def test_env_default_env_is_dev(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(app, ["framework", "symfony", "env", "--yes", str(tmp_path)])
    body = (tmp_path / ".env.local").read_text()
    assert "APP_ENV=dev" in body


def test_env_override_env(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(
        app, ["framework", "symfony", "env", "--yes", "--env", "prod", str(tmp_path)]
    )
    body = (tmp_path / ".env.local").read_text()
    assert "APP_ENV=prod" in body


def test_env_database_url_mysql(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(app, ["framework", "symfony", "env", "--yes", str(tmp_path)])
    body = (tmp_path / ".env.local").read_text()
    assert "DATABASE_URL=" in body
    assert "mysql://root:shimkit-dev@127.0.0.1:13306" in body
    assert "serverVersion=8.0" in body


def test_env_database_url_postgres(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(
        app, ["framework", "symfony", "env", "--yes", "--db", "postgres", str(tmp_path)]
    )
    body = (tmp_path / ".env.local").read_text()
    assert "postgresql://root:shimkit-dev@127.0.0.1:15432" in body
    assert "serverVersion=16" in body


def test_env_database_url_mariadb(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(
        app, ["framework", "symfony", "env", "--yes", "--db", "mariadb", str(tmp_path)]
    )
    body = (tmp_path / ".env.local").read_text()
    assert "mysql://root:shimkit-dev@127.0.0.1:13307" in body
    assert "mariadb-10.11" in body


def test_env_dry_run_no_write(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    result = runner.invoke(
        app, ["framework", "symfony", "env", "--dry-run", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert not (tmp_path / ".env.local").exists()


def test_env_app_secrets_are_unique(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    runner.invoke(app, ["framework", "symfony", "env", "--yes", str(a)])
    runner.invoke(app, ["framework", "symfony", "env", "--yes", str(b)])
    sa = next(
        ln for ln in (a / ".env.local").read_text().splitlines() if ln.startswith("APP_SECRET=")
    )
    sb = next(
        ln for ln in (b / ".env.local").read_text().splitlines() if ln.startswith("APP_SECRET=")
    )
    assert sa != sb


# ─── console / cache-clear ─────────────────────────────────────────────


def test_console_runs_bin_console_on_host(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_symfony_skeleton(tmp_path)
    monkeypatch.setattr(
        "shimkit.tools.framework.symfony.manager._vc.preflight",
        lambda *a, **kw: None,
    )
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.framework.symfony.manager.CommandRunner.run",
        staticmethod(fake_run),
    )
    result = runner.invoke(
        app,
        ["framework", "symfony", "console", "--project", str(tmp_path), "list"],
    )
    assert result.exit_code == 0, result.stdout
    assert seen and seen[0][0] == "php"
    assert seen[0][1].endswith("bin/console")
    assert seen[0][2] == "list"


def test_console_no_php_fails_69(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_symfony_skeleton(tmp_path)
    from shimkit.core import version as _vc

    def raising(_names):  # type: ignore[no-untyped-def]
        result = _vc.Result(
            tool="php",
            tool_version=None,
            constraint=_vc.VersionConstraint(),
            status=_vc.Status.MISSING,
            remediation="brew install php",
        )
        raise _vc.VersionViolationError([result])

    monkeypatch.setattr(
        "shimkit.tools.framework.symfony.manager._vc.preflight", raising
    )
    result = runner.invoke(
        app,
        ["framework", "symfony", "console", "--project", str(tmp_path), "list"],
    )
    assert result.exit_code == 69


def test_console_rejects_no_args(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_symfony_skeleton(tmp_path)
    result = runner.invoke(
        app, ["framework", "symfony", "console", "--project", str(tmp_path)]
    )
    assert result.exit_code == 1


def test_console_missing_bin_console(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    # No bin/console — not a Symfony project.
    monkeypatch.setattr(
        "shimkit.tools.framework.symfony.manager._vc.preflight",
        lambda *a, **kw: None,
    )
    result = runner.invoke(
        app,
        ["framework", "symfony", "console", "--project", str(tmp_path), "list"],
    )
    assert result.exit_code == 1
    assert "bin/console" in result.output.lower()


def test_console_in_container_delegates_to_stack(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_symfony_skeleton(tmp_path)

    seen: dict[str, object] = {}

    class FakeLemp:
        def exec_(self, *, cmd, project):  # type: ignore[no-untyped-def]
            seen["cmd"] = cmd
            seen["project"] = project
            return 0

    class FakeStackManager:
        @classmethod
        def create(cls):
            return cls()

        def boot(self):
            return self

        def lemp(self):
            return FakeLemp()

    monkeypatch.setattr("shimkit.tools.stack.manager.StackManager", FakeStackManager)
    result = runner.invoke(
        app,
        [
            "framework",
            "symfony",
            "console",
            "--project",
            str(tmp_path),
            "--in-container",
            "--stack",
            "myapp",
            "cache:clear",
            "--env=prod",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert seen["cmd"] == ["php", "bin/console", "cache:clear", "--env=prod"]
    assert seen["project"] == "myapp"


def test_cache_clear_runs_console_with_env_flag(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_symfony_skeleton(tmp_path)
    monkeypatch.setattr(
        "shimkit.tools.framework.symfony.manager._vc.preflight",
        lambda *a, **kw: None,
    )
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.framework.symfony.manager.CommandRunner.run",
        staticmethod(fake_run),
    )
    result = runner.invoke(
        app, ["framework", "symfony", "cache-clear", "--env", "prod", str(tmp_path)]
    )
    assert result.exit_code == 0
    # The cache-clear command runs `php bin/console cache:clear --env=prod`.
    assert seen and "cache:clear" in seen[0]
    assert "--env=prod" in seen[0]


# ─── command surface ────────────────────────────────────────────────────


def test_framework_help_lists_symfony(runner: CliRunner) -> None:
    result = runner.invoke(app, ["framework", "--help"])
    assert result.exit_code == 0
    assert "symfony" in result.output.lower()
    assert "laravel" in result.output.lower()


def test_symfony_help_lists_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["framework", "symfony", "--help"])
    assert result.exit_code == 0
    for sub in ("perms", "env", "cache-clear", "console"):
        assert sub in result.output
