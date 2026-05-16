"""Tests for ``shimkit framework django``.

Mirrors the Laravel + Symfony test shapes: platform gating, perms
with group detection, env scaffold (with SECRET_KEY shape +
DATABASE_URL for each engine), migrate delegation, manage host vs
container paths.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult
from shimkit.core.platform import Platform
from shimkit.tools.framework.django.manager import (
    DjangoManager,
    _generate_secret_key,
)

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
    python_present: bool = True,
) -> list[list[str]]:
    """Capture every CommandRunner.run; pretend getent/dscl resolve
    for the configured group when group_exists is True."""
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
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.framework.django.manager.CommandRunner.run",
        staticmethod(fake_run),
    )
    monkeypatch.setattr(
        "shimkit.tools.framework.django.manager.shutil.which",
        lambda name: f"/usr/bin/{name}" if name == "getent" else None,
    )
    return calls


def _make_django_skeleton(root: Path) -> None:
    """Build a minimal directory that passes the 'looks-like-Django' check."""
    (root / "media").mkdir(parents=True)
    (root / "staticfiles").mkdir()
    (root / "manage.py").write_text("#!/usr/bin/env python\n", encoding="utf-8")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── _generate_secret_key (pure) ──────────────────────────────────────


def test_generate_secret_key_default_length() -> None:
    key = _generate_secret_key()
    assert len(key) == 50


def test_generate_secret_key_uses_django_alphabet() -> None:
    key = _generate_secret_key()
    # Django's alphabet is [a-zA-Z0-9!@#$%^&*(-_=+)].
    pattern = re.compile(r"^[A-Za-z0-9!@#$%^&*()_\-+=]+$")
    assert pattern.match(key)


def test_generate_secret_key_uniqueness() -> None:
    """100 calls produce 100 distinct keys (probabilistic but
    overwhelming with the configured alphabet)."""
    keys = {_generate_secret_key() for _ in range(100)}
    assert len(keys) == 100


# ─── platform gating ────────────────────────────────────────────────────


def test_boot_exits_69_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Windows", machine="x86_64")),
    )
    with pytest.raises(SystemExit) as exc:
        DjangoManager.create().boot()
    assert exc.value.code == 69


def test_boot_accepts_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_unix(monkeypatch)
    assert DjangoManager.create().boot()._platform.is_linux


def test_boot_accepts_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_unix(monkeypatch, system="Darwin")
    assert DjangoManager.create().boot()._platform.is_macos


# ─── perms ──────────────────────────────────────────────────────────────


def test_perms_rejects_missing_path(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    result = runner.invoke(
        app, ["framework", "django", "perms", "--yes", str(tmp_path / "nope")]
    )
    assert result.exit_code == 1


def test_perms_dry_run(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    _make_django_skeleton(tmp_path)
    result = runner.invoke(
        app, ["framework", "django", "perms", "--dry-run", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "find" in result.stdout


def test_perms_targets_media_and_staticfiles(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Django's writable tree is media/ + staticfiles/."""
    _force_unix(monkeypatch)
    _make_django_skeleton(tmp_path)
    calls = _stub_runner(monkeypatch, group_exists=True)
    result = runner.invoke(
        app, ["framework", "django", "perms", "--yes", str(tmp_path)]
    )
    assert result.exit_code == 0, result.stdout
    flat = [" ".join(c) for c in calls]
    # chmod -R ug+rwx hits both media + staticfiles.
    media_chmod = [c for c in flat if "chmod -R ug+rwx" in c and c.endswith("/media")]
    static_chmod = [
        c for c in flat if "chmod -R ug+rwx" in c and c.endswith("/staticfiles")
    ]
    assert len(media_chmod) == 1
    assert len(static_chmod) == 1


def test_perms_skips_chgrp_when_group_missing(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_django_skeleton(tmp_path)
    calls = _stub_runner(monkeypatch, group_exists=False)
    result = runner.invoke(
        app, ["framework", "django", "perms", "--yes", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert not any(c and c[0] == "chgrp" for c in calls)


def test_perms_warns_on_missing_writable(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fresh Django projects don't have staticfiles/ until first
    collectstatic — perms should warn but still run."""
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    # Only media exists.
    (tmp_path / "media").mkdir()
    (tmp_path / "manage.py").write_text("#!/usr/bin/env python\n")
    result = runner.invoke(
        app, ["framework", "django", "perms", "--yes", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "haven't run" in result.stdout.lower() or "don't exist" in result.stdout.lower()


def test_perms_json_failed_steps(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_django_skeleton(tmp_path)

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        cmd_l = list(cmd) if not isinstance(cmd, str) else cmd.split()
        if cmd_l[:2] == ["getent", "group"]:
            return CommandResult(0, "www-data:x:33:\n", "")
        if cmd_l[0] == "chgrp":
            return CommandResult(1, "", "permission denied")
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.framework.django.manager.CommandRunner.run",
        staticmethod(fake_run),
    )
    monkeypatch.setattr(
        "shimkit.tools.framework.django.manager.shutil.which",
        lambda name: "/usr/bin/getent" if name == "getent" else None,
    )
    result = runner.invoke(
        app, ["framework", "django", "perms", "--yes", "--json", str(tmp_path)]
    )
    assert result.exit_code == 1
    doc = json.loads(result.output)
    assert doc["data"]["failed"]


# ─── env scaffold ──────────────────────────────────────────────────────


def test_env_refuses_overwrite(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    (tmp_path / ".env").write_text("existing\n")
    result = runner.invoke(
        app, ["framework", "django", "env", "--yes", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "refusing to overwrite" in result.output.lower()


def test_env_writes_secret_key_and_database_url(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    result = runner.invoke(
        app, ["framework", "django", "env", "--yes", str(tmp_path)]
    )
    assert result.exit_code == 0, result.stdout
    body = (tmp_path / ".env").read_text()
    # SECRET_KEY present + 50 chars long.
    line = next(ln for ln in body.splitlines() if ln.startswith("SECRET_KEY="))
    secret = line.split("=", 1)[1]
    assert len(secret) == 50
    # Default DB is postgres on :15432.
    assert "DATABASE_URL=" in body
    assert "postgres://root:shimkit-dev@127.0.0.1:15432" in body


def test_env_debug_true_by_default(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(app, ["framework", "django", "env", "--yes", str(tmp_path)])
    body = (tmp_path / ".env").read_text()
    assert "DEBUG=True" in body


def test_env_no_debug_flag(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(
        app, ["framework", "django", "env", "--yes", "--no-debug", str(tmp_path)]
    )
    body = (tmp_path / ".env").read_text()
    assert "DEBUG=False" in body


def test_env_database_url_mysql(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(
        app, ["framework", "django", "env", "--yes", "--db", "mysql", str(tmp_path)]
    )
    body = (tmp_path / ".env").read_text()
    assert "mysql://root:shimkit-dev@127.0.0.1:13306" in body


def test_env_database_url_mariadb(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(
        app, ["framework", "django", "env", "--yes", "--db", "mariadb", str(tmp_path)]
    )
    body = (tmp_path / ".env").read_text()
    assert "mysql://root:shimkit-dev@127.0.0.1:13307" in body


def test_env_includes_allowed_hosts_and_email(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(app, ["framework", "django", "env", "--yes", str(tmp_path)])
    body = (tmp_path / ".env").read_text()
    assert "ALLOWED_HOSTS=" in body
    assert "EMAIL_BACKEND=" in body


def test_env_redis_url_commented_out(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The starter env mentions Redis as a commented-out hint
    pointing the user at `shimkit db redis up`."""
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    runner.invoke(app, ["framework", "django", "env", "--yes", str(tmp_path)])
    body = (tmp_path / ".env").read_text()
    assert "REDIS_URL" in body
    assert "shimkit db redis up" in body


def test_env_dry_run_no_write(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    result = runner.invoke(
        app, ["framework", "django", "env", "--dry-run", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert not (tmp_path / ".env").exists()


def test_env_secret_keys_are_unique(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _stub_runner(monkeypatch)
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    runner.invoke(app, ["framework", "django", "env", "--yes", str(a)])
    runner.invoke(app, ["framework", "django", "env", "--yes", str(b)])
    sa = next(
        ln for ln in (a / ".env").read_text().splitlines() if ln.startswith("SECRET_KEY=")
    )
    sb = next(
        ln for ln in (b / ".env").read_text().splitlines() if ln.startswith("SECRET_KEY=")
    )
    assert sa != sb


# ─── manage / migrate ──────────────────────────────────────────────────


def test_manage_runs_manage_py_on_host(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_django_skeleton(tmp_path)
    monkeypatch.setattr(
        "shimkit.tools.framework.django.manager._vc.preflight",
        lambda *a, **kw: None,
    )
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.framework.django.manager.CommandRunner.run",
        staticmethod(fake_run),
    )
    result = runner.invoke(
        app,
        ["framework", "django", "manage", "--project", str(tmp_path), "showmigrations"],
    )
    assert result.exit_code == 0, result.stdout
    assert seen and seen[0][1].endswith("manage.py")
    assert "showmigrations" in seen[0]


def test_manage_no_python_fails_69(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_django_skeleton(tmp_path)
    from shimkit.core import version as _vc

    def raising(_names):  # type: ignore[no-untyped-def]
        result = _vc.Result(
            tool="python",
            tool_version=None,
            constraint=_vc.VersionConstraint(),
            status=_vc.Status.MISSING,
            remediation="brew install python@3.12",
        )
        raise _vc.VersionViolationError([result])

    monkeypatch.setattr(
        "shimkit.tools.framework.django.manager._vc.preflight", raising
    )
    result = runner.invoke(
        app,
        ["framework", "django", "manage", "--project", str(tmp_path), "showmigrations"],
    )
    assert result.exit_code == 69


def test_manage_rejects_no_args(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_django_skeleton(tmp_path)
    result = runner.invoke(
        app, ["framework", "django", "manage", "--project", str(tmp_path)]
    )
    assert result.exit_code == 1


def test_manage_missing_manage_py(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.framework.django.manager._vc.preflight",
        lambda *a, **kw: None,
    )
    # No manage.py.
    result = runner.invoke(
        app,
        ["framework", "django", "manage", "--project", str(tmp_path), "showmigrations"],
    )
    assert result.exit_code == 1
    assert "manage.py" in result.output.lower()


def test_manage_in_container_delegates_to_stack(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _make_django_skeleton(tmp_path)

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
            "django",
            "manage",
            "--project",
            str(tmp_path),
            "--in-container",
            "--stack",
            "myapp",
            "migrate",
            "--no-input",
        ],
    )
    assert result.exit_code == 0
    assert seen["cmd"] == ["python", "manage.py", "migrate", "--no-input"]
    assert seen["project"] == "myapp"


def test_migrate_wraps_manage_migrate(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`migrate` is sugar for `manage migrate --no-input`."""
    _force_unix(monkeypatch)
    _make_django_skeleton(tmp_path)
    monkeypatch.setattr(
        "shimkit.tools.framework.django.manager._vc.preflight",
        lambda *a, **kw: None,
    )
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.framework.django.manager.CommandRunner.run",
        staticmethod(fake_run),
    )
    result = runner.invoke(app, ["framework", "django", "migrate", str(tmp_path)])
    assert result.exit_code == 0
    assert "migrate" in seen[0]
    assert "--no-input" in seen[0]


# ─── command surface ────────────────────────────────────────────────────


def test_framework_help_lists_django(runner: CliRunner) -> None:
    result = runner.invoke(app, ["framework", "--help"])
    assert result.exit_code == 0
    assert "django" in result.output.lower()


def test_django_help_lists_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["framework", "django", "--help"])
    assert result.exit_code == 0
    for sub in ("perms", "env", "migrate", "manage"):
        assert sub in result.output
