"""Tests for ``shimkit db <engine> ... --on-host``.

Routes through HostService (systemd / brew services) rather than
DockerEnv. We mock the HostService at the manager boundary so
neither systemctl nor brew is invoked on the test host.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult, HostServiceResult
from shimkit.core.platform import Platform
from shimkit.tools.db.manager import DbManager

# ─── helpers ────────────────────────────────────────────────────────────


class _FakeHost:
    """In-memory HostService — records calls + returns canned outcomes."""

    def __init__(self, *, state: str = "stopped", start_ok: bool = True) -> None:
        self._state = state
        self._start_ok = start_ok
        self.calls: list[tuple[str, str]] = []

    def state(self, service: str):  # type: ignore[no-untyped-def]
        self.calls.append(("state", service))
        return self._state

    def start(self, service: str) -> HostServiceResult:
        self.calls.append(("start", service))
        if not self._start_ok:
            return HostServiceResult(ok=False, state="stopped", stderr="permission denied")
        self._state = "running"
        return HostServiceResult(ok=True, state="running")

    def stop(self, service: str) -> HostServiceResult:
        self.calls.append(("stop", service))
        self._state = "stopped"
        return HostServiceResult(ok=True, state="stopped")


def _force_unix(monkeypatch: pytest.MonkeyPatch, system: str = "Linux") -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system=system, machine="x86_64")),
    )


def _stub_host(monkeypatch: pytest.MonkeyPatch, host: _FakeHost) -> None:
    """Replace HostService.detect() at the manager-level import site."""

    class _Selector:
        @classmethod
        def detect(cls, platform=None):  # type: ignore[no-untyped-def]
            return host

    monkeypatch.setattr("shimkit.tools.db.manager.HostService", _Selector)


def _stub_which(monkeypatch: pytest.MonkeyPatch, *, present: set[str]) -> None:
    monkeypatch.setattr(
        "shimkit.tools.db.manager.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in present else None,
    )


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── boot ───────────────────────────────────────────────────────────────


def test_boot_on_host_skips_docker_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    """--on-host must NOT preflight docker (the user may not have it)."""
    called: list[bool] = []

    def fake_preflight(*a, **kw):  # type: ignore[no-untyped-def]
        called.append(True)

    monkeypatch.setattr("shimkit.core.version.preflight", fake_preflight)
    DbManager.create().boot(on_host=True)
    assert called == []


def test_boot_default_still_preflights_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without on_host=True, docker preflight runs as before."""
    called: list[bool] = []

    def fake_preflight(*a, **kw):  # type: ignore[no-untyped-def]
        called.append(True)

    monkeypatch.setattr("shimkit.core.version.preflight", fake_preflight)
    # Stub _from_env to avoid a real daemon connection.
    monkeypatch.setattr("shimkit.core.docker._from_env", lambda: object())
    DbManager.create().boot()
    assert called == [True]


# ─── refusals ───────────────────────────────────────────────────────────


def test_up_on_host_rejects_mongo(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch)
    _stub_host(monkeypatch, _FakeHost())
    result = runner.invoke(app, ["db", "mongo", "up", "--yes", "--on-host"])
    assert result.exit_code == 1
    assert "--on-host" in result.stdout.lower() or "on-host" in result.stdout.lower()


def test_up_on_host_rejects_phpmyadmin(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch)
    _stub_host(monkeypatch, _FakeHost())
    result = runner.invoke(app, ["db", "phpmyadmin", "up", "--yes", "--on-host"])
    assert result.exit_code == 1


def test_up_on_host_rejects_missing_binary(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch)
    _stub_host(monkeypatch, _FakeHost())
    _stub_which(monkeypatch, present=set())
    result = runner.invoke(app, ["db", "mysql", "up", "--yes", "--on-host"])
    assert result.exit_code == 1
    assert "not on path" in result.stdout.lower()


def test_up_on_host_rejects_unsupported_platform(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Windows", machine="x86_64")),
    )

    class _Selector:
        @classmethod
        def detect(cls, platform=None):  # type: ignore[no-untyped-def]
            return None  # No supported manager on Windows.

    monkeypatch.setattr("shimkit.tools.db.manager.HostService", _Selector)
    _stub_which(monkeypatch, present={"mysql"})
    result = runner.invoke(app, ["db", "mysql", "up", "--yes", "--on-host"])
    assert result.exit_code == 1
    assert "windows" in result.stdout.lower() or "macos or linux" in result.stdout.lower()


# ─── up / down / status ─────────────────────────────────────────────────


def test_up_on_host_starts_linux_service(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch, system="Linux")
    host = _FakeHost(state="stopped")
    _stub_host(monkeypatch, host)
    _stub_which(monkeypatch, present={"mysql"})
    result = runner.invoke(app, ["db", "mysql", "up", "--yes", "--on-host"])
    assert result.exit_code == 0, result.stdout
    assert ("start", "mysql") in host.calls


def test_up_on_host_starts_macos_service_using_brew_name(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch, system="Darwin")
    host = _FakeHost(state="stopped")
    _stub_host(monkeypatch, host)
    _stub_which(monkeypatch, present={"psql"})
    result = runner.invoke(app, ["db", "postgres", "up", "--yes", "--on-host"])
    assert result.exit_code == 0, result.stdout
    # macOS service name comes from host_services.postgres.service_macos
    assert ("start", "postgresql@16") in host.calls


def test_up_on_host_dry_run_does_not_call_start(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch)
    host = _FakeHost(state="stopped")
    _stub_host(monkeypatch, host)
    _stub_which(monkeypatch, present={"mysql"})
    result = runner.invoke(
        app, ["db", "mysql", "up", "--yes", "--on-host", "--dry-run"]
    )
    assert result.exit_code == 0
    assert not any(c[0] == "start" for c in host.calls)


def test_up_on_host_failed_start_returns_1(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch)
    host = _FakeHost(state="stopped", start_ok=False)
    _stub_host(monkeypatch, host)
    _stub_which(monkeypatch, present={"mysql"})
    result = runner.invoke(app, ["db", "mysql", "up", "--yes", "--on-host"])
    assert result.exit_code == 1
    assert "permission denied" in result.stdout


def test_down_on_host_stops_service(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch)
    host = _FakeHost(state="running")
    _stub_host(monkeypatch, host)
    _stub_which(monkeypatch, present={"mysql"})
    result = runner.invoke(app, ["db", "mysql", "down", "--yes", "--on-host"])
    assert result.exit_code == 0, result.stdout
    assert ("stop", "mysql") in host.calls


def test_down_on_host_dry_run_does_not_call_stop(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch)
    host = _FakeHost(state="running")
    _stub_host(monkeypatch, host)
    _stub_which(monkeypatch, present={"mysql"})
    result = runner.invoke(
        app, ["db", "mysql", "down", "--yes", "--on-host", "--dry-run"]
    )
    assert result.exit_code == 0
    assert not any(c[0] == "stop" for c in host.calls)


def test_status_on_host_reports_state(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch)
    host = _FakeHost(state="running")
    _stub_host(monkeypatch, host)
    _stub_which(monkeypatch, present={"mysql"})
    result = runner.invoke(app, ["db", "mysql", "status", "--on-host", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["mode"] == "on-host"
    assert doc["data"]["state"] == "running"
    assert doc["data"]["service"] == "mysql"


def test_status_on_host_works_when_binary_missing(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """status is read-only — the service file may exist even when the client isn't on PATH."""
    _force_unix(monkeypatch)
    host = _FakeHost(state="stopped")
    _stub_host(monkeypatch, host)
    _stub_which(monkeypatch, present=set())  # no mysql client
    result = runner.invoke(app, ["db", "mysql", "status", "--on-host", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["state"] == "stopped"


# ─── shell --on-host ────────────────────────────────────────────────────


def test_shell_on_host_rejects_unsupported_engine(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch)
    result = runner.invoke(app, ["db", "mongo", "shell", "--on-host"])
    assert result.exit_code == 1


def test_shell_on_host_rejects_missing_client(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch)
    _stub_which(monkeypatch, present=set())
    result = runner.invoke(app, ["db", "mysql", "shell", "--on-host"])
    assert result.exit_code == 69
    assert "not on path" in result.stdout.lower()


def test_shell_on_host_invokes_client_argv(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch)
    _stub_which(monkeypatch, present={"mysql"})
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd) if not isinstance(cmd, str) else cmd.split())
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.db.manager.CommandRunner.run", staticmethod(fake_run)
    )
    result = runner.invoke(app, ["db", "mysql", "shell", "--on-host"])
    assert result.exit_code == 0, result.stdout
    assert seen and seen[0][0] == "mysql"
    assert "-h" in seen[0] and "127.0.0.1" in seen[0]


def test_shell_on_host_postgres_uses_psql_with_pgpassword(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_unix(monkeypatch)
    _stub_which(monkeypatch, present={"psql"})
    seen: list[dict[str, object]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append({"cmd": list(cmd), **kw})
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.db.manager.CommandRunner.run", staticmethod(fake_run)
    )
    result = runner.invoke(
        app, ["db", "postgres", "shell", "--on-host", "--password", "secret"]
    )
    assert result.exit_code == 0, result.stdout
    call = seen[0]
    assert call["cmd"][0] == "psql"
    env = call.get("env")
    assert isinstance(env, dict)
    assert env["PGPASSWORD"] == "secret"


# ─── engine driver layer ────────────────────────────────────────────────


def test_engine_supports_on_host_table() -> None:
    """Only mysql/mariadb/postgres opt into --on-host."""
    from shimkit.tools.db import engines as _engines

    on_host = {n for n in _engines.REGISTRY if _engines.get(n).supports_on_host()}
    assert on_host == {"mysql", "mariadb", "postgres"}


def test_engine_host_shell_argv_targets_127001() -> None:
    from shimkit.tools.db import engines as _engines

    for name in ("mysql", "mariadb"):
        argv = _engines.get(name).host_shell_argv(password="pw")
        assert "-h" in argv and "127.0.0.1" in argv
        assert any(a.startswith("-p") for a in argv)


def test_engine_postgres_host_client_binary() -> None:
    from shimkit.tools.db import engines as _engines

    assert _engines.get("postgres").host_client_binary() == "psql"
