"""Tests for ``shimkit framework laravel``."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult
from shimkit.core.platform import Platform
from shimkit.tools.framework.laravel.manager import LaravelManager

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
    """Capture every CommandRunner.run call into a list; pretend
    `getent group <name>` resolves when group_exists=True; pretend
    `php` returns version output when php_present=True. Also pins
    `shutil.which` to a deterministic path so group detection takes
    the `getent` branch exclusively (no real-OS `grp` fallback).
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
        "shimkit.tools.framework.laravel.manager.CommandRunner.run",
        staticmethod(fake_run),
    )
    monkeypatch.setattr(
        "shimkit.tools.framework.laravel.manager.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in ("getent", "php") else None,
    )
    return calls


def _make_laravel_skeleton(root: Path) -> None:
    """Make a minimal directory that passes our `looks-like-Laravel` checks."""
    (root / "storage").mkdir(parents=True)
    (root / "bootstrap" / "cache").mkdir(parents=True)
    (root / "artisan").write_text("#!/usr/bin/env php\n<?php\n", encoding="utf-8")


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
        LaravelManager.create().boot()
    assert exc.value.code == 69


def test_boot_accepts_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_unix(monkeypatch)
    mgr = LaravelManager.create().boot()
    assert mgr._platform is not None
    assert mgr._platform.is_linux


def test_boot_accepts_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_unix(monkeypatch, system="Darwin")
    mgr = LaravelManager.create().boot()
    assert mgr._platform.is_macos


# ─── perms ──────────────────────────────────────────────────────────────


def test_perms_rejects_missing_path(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    nonexistent = tmp_path / "nope"
    result = runner.invoke(app, ["framework", "laravel", "perms", "--yes", str(nonexistent)])
    assert result.exit_code == 1
    assert "Not a directory" in result.stdout


def test_perms_dry_run_lists_commands(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    _make_laravel_skeleton(tmp_path)
    result = runner.invoke(
        app, ["framework", "laravel", "perms", "--dry-run", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "find" in result.stdout
    assert "chmod" in result.stdout
    # No actual run happens.
    # (--dry-run avoids the MODERATE prompt — short-circuit on dry_run.)


def test_perms_invokes_find_chmod_chgrp(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_laravel_skeleton(tmp_path)
    calls = _stub_runner(monkeypatch, group_exists=True)
    result = runner.invoke(app, ["framework", "laravel", "perms", "--yes", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    flat = [" ".join(c) for c in calls]
    assert any("find" in c and "-exec chmod 664" in c for c in flat)
    assert any("find" in c and "-exec chmod 775" in c for c in flat)
    assert any("chgrp -R www-data" in c for c in flat)
    assert any("chmod -R ug+rwx" in c for c in flat)


def test_perms_skips_chgrp_when_group_missing(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_laravel_skeleton(tmp_path)
    calls = _stub_runner(monkeypatch, group_exists=False)
    result = runner.invoke(app, ["framework", "laravel", "perms", "--yes", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    # Check argv[0], not a joined-path substring (tmp_path name can contain "chgrp").
    assert not any(c and c[0] == "chgrp" for c in calls)


def test_perms_group_flag_overrides_config(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_laravel_skeleton(tmp_path)
    calls = _stub_runner(monkeypatch, group_exists=True)
    result = runner.invoke(
        app,
        ["framework", "laravel", "perms", "--yes", "--group", "staff", str(tmp_path)],
    )
    assert result.exit_code == 0, result.stdout
    flat = [" ".join(c) for c in calls]
    assert any("chgrp -R staff" in c for c in flat)


def test_perms_warns_on_missing_writable_dirs(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    (tmp_path / "artisan").write_text("#!/usr/bin/env php\n", encoding="utf-8")
    result = runner.invoke(app, ["framework", "laravel", "perms", "--yes", str(tmp_path)])
    # Missing storage/ + bootstrap/cache emits a warning but still
    # runs the global chmod find passes.
    assert result.exit_code == 0
    assert "don't exist" in result.stdout


def test_perms_json_output_reports_failed_steps(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_laravel_skeleton(tmp_path)

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        cmd_l = list(cmd) if not isinstance(cmd, str) else cmd.split()
        if cmd_l[:2] == ["getent", "group"]:
            return CommandResult(0, "www-data:x:33:\n", "")
        if cmd_l[0] == "chgrp":
            return CommandResult(1, "", "operation not permitted")
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.framework.laravel.manager.CommandRunner.run",
        staticmethod(fake_run),
    )
    result = runner.invoke(
        app, ["framework", "laravel", "perms", "--yes", "--json", str(tmp_path)]
    )
    assert result.exit_code == 1
    doc = json.loads(result.stdout)
    assert doc["data"]["failed"]
    assert any("chgrp" in line for line in doc["data"]["failed"])


# ─── env ────────────────────────────────────────────────────────────────


def test_env_scaffold_refuses_overwrite(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    (tmp_path / ".env").write_text("existing content\n", encoding="utf-8")
    result = runner.invoke(app, ["framework", "laravel", "env", "--yes", str(tmp_path)])
    assert result.exit_code == 1
    assert "refusing to overwrite" in result.stdout


def test_env_scaffold_writes_app_key(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    result = runner.invoke(app, ["framework", "laravel", "env", "--yes", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    env = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "APP_KEY=base64:" in env
    # APP_KEY must decode to exactly 32 bytes.
    key_line = next(line for line in env.splitlines() if line.startswith("APP_KEY="))
    encoded = key_line.split("=", 1)[1].removeprefix("base64:")
    assert len(base64.b64decode(encoded)) == 32


def test_env_scaffold_app_name_defaults_to_dirname(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    project = tmp_path / "myshop"
    project.mkdir()
    result = runner.invoke(app, ["framework", "laravel", "env", "--yes", str(project)])
    assert result.exit_code == 0, result.stdout
    body = (project / ".env").read_text()
    assert "APP_NAME=myshop" in body
    assert "DB_DATABASE=myshop" in body


def test_env_scaffold_db_postgres_swaps_connection_and_port(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    result = runner.invoke(
        app,
        ["framework", "laravel", "env", "--yes", "--db", "postgres", str(tmp_path)],
    )
    assert result.exit_code == 0
    body = (tmp_path / ".env").read_text()
    assert "DB_CONNECTION=pgsql" in body
    assert "DB_PORT=15432" in body


def test_env_scaffold_mysql_default(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(app, ["framework", "laravel", "env", "--yes", str(tmp_path)])
    body = (tmp_path / ".env").read_text()
    assert "DB_CONNECTION=mysql" in body
    assert "DB_PORT=13306" in body


def test_env_scaffold_mariadb_uses_dedicated_port(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(
        app, ["framework", "laravel", "env", "--yes", "--db", "mariadb", str(tmp_path)]
    )
    body = (tmp_path / ".env").read_text()
    assert "DB_CONNECTION=mysql" in body  # mariadb uses mysql driver
    assert "DB_PORT=13307" in body


def test_env_scaffold_dry_run_writes_nothing(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    result = runner.invoke(
        app, ["framework", "laravel", "env", "--dry-run", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert not (tmp_path / ".env").exists()


def test_env_scaffold_rejects_missing_project_dir(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    missing = tmp_path / "missing"
    result = runner.invoke(app, ["framework", "laravel", "env", "--yes", str(missing)])
    assert result.exit_code == 1


def test_env_scaffold_app_key_is_unique(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    runner.invoke(app, ["framework", "laravel", "env", "--yes", str(a)])
    runner.invoke(app, ["framework", "laravel", "env", "--yes", str(b)])
    key_a = next(
        ln for ln in (a / ".env").read_text().splitlines() if ln.startswith("APP_KEY=")
    )
    key_b = next(
        ln for ln in (b / ".env").read_text().splitlines() if ln.startswith("APP_KEY=")
    )
    assert key_a != key_b


# ─── cron-install ───────────────────────────────────────────────────────


def test_cron_install_requires_artisan_binary(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    (tmp_path / "storage").mkdir()  # not a Laravel root — no `artisan`
    result = runner.invoke(
        app, ["framework", "laravel", "cron-install", "--yes", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "artisan" in result.stdout.lower()


def test_cron_install_delegates_to_cron_manager(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    _make_laravel_skeleton(tmp_path)

    seen: dict[str, object] = {}

    class FakeCronManager:
        @classmethod
        def create(cls):
            return cls()

        def boot(self):
            return self

        def add(self, **kw):  # type: ignore[no-untyped-def]
            seen.update(kw)
            return 0

    monkeypatch.setattr("shimkit.tools.cron.manager.CronManager", FakeCronManager)
    result = runner.invoke(
        app,
        ["framework", "laravel", "cron-install", "--yes", "--dry-run", str(tmp_path)],
    )
    assert result.exit_code == 0, result.stdout
    # `--dry-run` is passed straight through to CronManager.add.
    assert seen.get("dry_run") is True
    assert seen.get("schedule") == "* * * * *"
    assert "schedule:run" in str(seen.get("command"))


def test_cron_install_uses_custom_name_and_schedule(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    _make_laravel_skeleton(tmp_path)
    seen: dict[str, object] = {}

    class FakeCronManager:
        @classmethod
        def create(cls):
            return cls()

        def boot(self):
            return self

        def add(self, **kw):  # type: ignore[no-untyped-def]
            seen.update(kw)
            return 0

    monkeypatch.setattr("shimkit.tools.cron.manager.CronManager", FakeCronManager)
    result = runner.invoke(
        app,
        [
            "framework",
            "laravel",
            "cron-install",
            "--yes",
            "--dry-run",
            "--name",
            "myshop-scheduler",
            "--schedule",
            "*/5 * * * *",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert seen.get("name") == "myshop-scheduler"
    assert seen.get("schedule") == "*/5 * * * *"


def test_cron_install_command_includes_project_cd(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    project = tmp_path / "myshop"
    project.mkdir()
    _make_laravel_skeleton(project)
    seen: dict[str, object] = {}

    class FakeCronManager:
        @classmethod
        def create(cls):
            return cls()

        def boot(self):
            return self

        def add(self, **kw):  # type: ignore[no-untyped-def]
            seen.update(kw)
            return 0

    monkeypatch.setattr("shimkit.tools.cron.manager.CronManager", FakeCronManager)
    runner.invoke(
        app,
        ["framework", "laravel", "cron-install", "--yes", "--dry-run", str(project)],
    )
    assert f"cd {project}" in str(seen.get("command"))


# ─── artisan ────────────────────────────────────────────────────────────


def test_artisan_runs_on_host_when_php_available(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_laravel_skeleton(tmp_path)
    monkeypatch.setattr(
        "shimkit.tools.framework.laravel.manager.shutil.which",
        lambda name: "/usr/bin/php" if name == "php" else None,
    )

    seen: list[list[str]] = []

    def fake_preflight(_names):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(
        "shimkit.tools.framework.laravel.manager._vc.preflight",
        fake_preflight,
    )

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.framework.laravel.manager.CommandRunner.run",
        staticmethod(fake_run),
    )
    result = runner.invoke(
        app,
        ["framework", "laravel", "artisan", "--project", str(tmp_path), "migrate"],
    )
    assert result.exit_code == 0, result.stdout
    assert seen and seen[0][:3] == ["php", "artisan", "migrate"]


def test_artisan_fails_without_php(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_laravel_skeleton(tmp_path)
    monkeypatch.setattr(
        "shimkit.tools.framework.laravel.manager.shutil.which",
        lambda _: None,
    )
    # Make preflight raise like a missing tool.
    from shimkit.core import version as _vc

    def raising_preflight(_names):  # type: ignore[no-untyped-def]
        result = _vc.Result(
            tool="php",
            tool_version=None,
            constraint=_vc.VersionConstraint(),
            status=_vc.Status.MISSING,
            remediation="brew install php",
        )
        raise _vc.VersionViolationError([result])

    monkeypatch.setattr(
        "shimkit.tools.framework.laravel.manager._vc.preflight",
        raising_preflight,
    )
    result = runner.invoke(
        app,
        ["framework", "laravel", "artisan", "--project", str(tmp_path), "migrate"],
    )
    assert result.exit_code == 69
    assert "php" in result.stdout.lower()


def test_artisan_rejects_no_args(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_laravel_skeleton(tmp_path)
    result = runner.invoke(
        app, ["framework", "laravel", "artisan", "--project", str(tmp_path)]
    )
    assert result.exit_code == 1


def test_artisan_in_container_delegates_to_stack(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_laravel_skeleton(tmp_path)

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
            "laravel",
            "artisan",
            "--project",
            str(tmp_path),
            "--in-container",
            "--stack",
            "myshop",
            "migrate",
            "--seed",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert seen["cmd"] == ["php", "artisan", "migrate", "--seed"]
    assert seen["project"] == "myshop"


# ─── env body shape ─────────────────────────────────────────────────────


def test_env_body_contains_expected_keys(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(app, ["framework", "laravel", "env", "--yes", str(tmp_path)])
    body = (tmp_path / ".env").read_text()
    for key in (
        "APP_NAME=",
        "APP_ENV=",
        "APP_KEY=",
        "APP_DEBUG=",
        "DB_CONNECTION=",
        "DB_HOST=",
        "DB_PORT=",
        "DB_DATABASE=",
        "DB_USERNAME=",
        "DB_PASSWORD=",
        "CACHE_DRIVER=",
        "QUEUE_CONNECTION=",
        "SESSION_DRIVER=",
        "MAIL_MAILER=",
    ):
        assert key in body, f"missing {key}"


def test_env_default_env_is_local(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(app, ["framework", "laravel", "env", "--yes", str(tmp_path)])
    body = (tmp_path / ".env").read_text()
    assert "APP_ENV=local" in body


def test_env_override_env_value(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(
        app, ["framework", "laravel", "env", "--yes", "--env", "staging", str(tmp_path)]
    )
    body = (tmp_path / ".env").read_text()
    assert "APP_ENV=staging" in body


# ─── command surface ────────────────────────────────────────────────────


def test_framework_help_lists_laravel(runner: CliRunner) -> None:
    result = runner.invoke(app, ["framework", "--help"])
    assert result.exit_code == 0
    assert "laravel" in result.output.lower()


def test_laravel_help_lists_all_four_commands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["framework", "laravel", "--help"])
    assert result.exit_code == 0
    for sub in ("perms", "env", "cron-install", "artisan"):
        assert sub in result.output


def test_php_in_versions_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `php` detector is registered with a min constraint."""
    from shimkit.config import get_config
    from shimkit.core import version as _vc

    assert "php" in _vc._DETECTORS
    assert get_config().tools.versions.php.min == "8.1"
