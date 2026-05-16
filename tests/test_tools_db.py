"""Tests for ``shimkit db``.

DockerEnv is mocked end-to-end; no real daemon is invoked. The
engine drivers are pure value-producers (`environment_for_up`,
`shell_argv`, `dump_argv`) and get fixture-style tests.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult
from shimkit.tools.db import engines
from shimkit.tools.db.engines.base import UnsupportedEngineOperationError
from shimkit.tools.db.manager import DbManager

# ─── helpers ────────────────────────────────────────────────────────────


class _NotFound(Exception):  # noqa: N818 — stand-in for docker.errors.NotFound
    pass


@pytest.fixture(autouse=True)
def _docker_errors_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    docker_errors = types.ModuleType("docker.errors")
    docker_errors.NotFound = _NotFound  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "docker.errors", docker_errors)


def _stub_docker_env(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace _from_env() so DockerEnv.boot() returns a mock client."""
    client = MagicMock()
    monkeypatch.setattr("shimkit.core.docker._from_env", lambda: client)
    return client


def _bypass_version_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `version.preflight(("docker",))` always succeed."""
    monkeypatch.setattr(
        "shimkit.core.version.preflight",
        lambda tools, force=False, runner=None: None,
    )


def _container_mock(
    *, name: str, status: str = "running", image_tag: str = "mysql:8.0", ports: Any = None
) -> MagicMock:
    c = MagicMock()
    c.name = name
    c.status = status
    img = MagicMock()
    img.tags = [image_tag]
    c.image = img
    c.ports = ports or {}
    return c


# ─── engine drivers — pure ─────────────────────────────────────────────


def test_mysql_engine_env_for_up() -> None:
    e = engines.get("mysql")
    assert e is not None
    env = e.environment_for_up(password="hunter2")
    assert env["MYSQL_ROOT_PASSWORD"] == "hunter2"
    assert e.container_port == 3306
    assert e.data_dir() == "/var/lib/mysql"


def test_mysql_shell_and_dump_argv() -> None:
    e = engines.get("mysql")
    assert e is not None
    assert e.shell_argv(password="pw") == ["mysql", "-uroot", "-ppw"]
    assert "mysqldump" in e.dump_argv(password="pw")
    assert "-ppw" in e.dump_argv(password="pw")


def test_mariadb_engine_uses_mariadb_password_var() -> None:
    e = engines.get("mariadb")
    assert e is not None
    env = e.environment_for_up(password="pw")
    assert env["MARIADB_ROOT_PASSWORD"] == "pw"
    assert e.shell_argv(password="pw")[0] == "mariadb"
    assert e.dump_argv(password="pw")[0] == "mariadb-dump"


def test_postgres_engine_uses_postgres_password_var() -> None:
    e = engines.get("postgres")
    assert e is not None
    env = e.environment_for_up(password="pw")
    assert env["POSTGRES_PASSWORD"] == "pw"
    assert env["POSTGRES_USER"] == "postgres"
    assert e.shell_argv(password="pw") == ["psql", "-U", "postgres"]
    assert e.data_dir() == "/var/lib/postgresql/data"


def test_mongo_engine_uses_mongo_initdb_vars() -> None:
    e = engines.get("mongo")
    assert e is not None
    env = e.environment_for_up(password="pw")
    assert env["MONGO_INITDB_ROOT_USERNAME"] == "admin"
    assert env["MONGO_INITDB_ROOT_PASSWORD"] == "pw"
    assert e.shell_argv(password="pw")[0] == "mongosh"
    assert "--archive" in e.dump_argv(password="pw")


def test_phpmyadmin_engine_routes_through_host_docker_internal() -> None:
    e = engines.get("phpmyadmin")
    assert e is not None
    env = e.environment_for_up(password="pw", extras={"link_port": "13306"})
    assert env["PMA_HOST"] == "host.docker.internal"
    assert env["PMA_PORT"] == "13306"
    assert env["PMA_USER"] == "root"
    assert e.supports_shell() is False
    assert e.supports_dump() is False


def test_phpmyadmin_no_volume_mount_regardless_of_arg() -> None:
    e = engines.get("phpmyadmin")
    assert e is not None
    # Caller may pass volume_root; engine refuses (stateless).
    assert e.volume_mounts(volume_root="/tmp/x") == {}


def test_phpmyadmin_shell_raises_unsupported() -> None:
    e = engines.get("phpmyadmin")
    assert e is not None
    with pytest.raises(UnsupportedEngineOperationError):
        e.shell_argv(password="pw")
    with pytest.raises(UnsupportedEngineOperationError):
        e.dump_argv(password="pw")


# ─── DbManager boot ─────────────────────────────────────────────────────


def test_boot_exits_69_when_docker_version_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.core.docker._from_env", lambda: MagicMock())
    # Force the version preflight to fail with MISSING.
    monkeypatch.setattr("shimkit.core.version.shutil.which", lambda _b: None)
    with pytest.raises(SystemExit) as exc:
        DbManager.create().boot()
    assert exc.value.code == 69


def test_boot_exits_69_when_daemon_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    from shimkit.core.docker import DockerNotAvailableError

    def raise_unavailable() -> Any:
        raise DockerNotAvailableError("daemon down")

    monkeypatch.setattr("shimkit.core.docker._from_env", raise_unavailable)
    with pytest.raises(SystemExit) as exc:
        DbManager.create().boot()
    assert exc.value.code == 69


def test_boot_succeeds_when_everything_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    _stub_docker_env(monkeypatch)
    mgr = DbManager.create().boot()
    assert mgr is not None


# ─── up ─────────────────────────────────────────────────────────────────


def test_db_mysql_up_creates_container_with_right_args(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.side_effect = _NotFound("absent")
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(
        app,
        [
            "db",
            "mysql",
            "up",
            "--yes",
            "--port",
            "13306",
            "--password",
            "test-pw",
            "--json",
        ],
    )
    assert result.exit_code == 0
    client.containers.run.assert_called_once()
    _, kw = client.containers.run.call_args
    assert kw["name"] == "shimkit-db-mysql-dev"
    assert kw["environment"]["MYSQL_ROOT_PASSWORD"] == "test-pw"
    # Port: container 3306/tcp → host (127.0.0.1, 13306)
    binding = kw["ports"]["3306/tcp"]
    assert binding == ("127.0.0.1", 13306)


def test_db_up_dry_run_does_not_invoke_docker(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.side_effect = _NotFound("absent")
    result = runner.invoke(app, ["db", "postgres", "up", "--yes", "--dry-run"])
    assert result.exit_code == 0
    client.containers.run.assert_not_called()


def test_db_up_already_running_is_noop(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.return_value = _container_mock(
        name="shimkit-db-postgres-dev", status="running"
    )
    result = runner.invoke(app, ["db", "postgres", "up", "--yes", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["action"] == "already_running"
    client.containers.run.assert_not_called()


def test_db_up_existing_stopped_calls_start(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    fake = _container_mock(name="shimkit-db-mongo-dev", status="exited")
    client.containers.get.return_value = fake
    result = runner.invoke(app, ["db", "mongo", "up", "--yes", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["action"] == "started"
    fake.start.assert_called_once()
    client.containers.run.assert_not_called()


def test_db_up_refuses_under_no_input(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    _stub_docker_env(monkeypatch)
    result = runner.invoke(app, ["db", "--no-input", "mysql", "up"])
    assert result.exit_code == 1


def test_db_up_ephemeral_skips_volume(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.side_effect = _NotFound("absent")
    result = runner.invoke(app, ["db", "mysql", "up", "--yes", "--ephemeral", "--json"])
    assert result.exit_code == 0
    _, kw = client.containers.run.call_args
    assert kw["volumes"] is None


def test_db_up_custom_id_changes_container_name(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.side_effect = _NotFound("absent")
    result = runner.invoke(app, ["db", "mysql", "up", "--yes", "--name", "qa", "--json"])
    assert result.exit_code == 0
    _, kw = client.containers.run.call_args
    assert kw["name"] == "shimkit-db-mysql-qa"


def test_db_up_for_unknown_engine_errors() -> None:
    # The Typer registry only knows the registered engines; an
    # unknown sub-app name gives Typer's usage error. `redis` joined
    # the registry in v0.15.0, so we use a name that's definitely
    # not in the list.
    runner = CliRunner()
    result = runner.invoke(app, ["db", "elasticsearch", "up"])
    assert result.exit_code == 2  # Typer usage error


# ─── down ───────────────────────────────────────────────────────────────


def test_db_down_stops_and_removes(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    fake = _container_mock(name="shimkit-db-mysql-dev")
    client.containers.get.return_value = fake
    result = runner.invoke(app, ["db", "mysql", "down", "--yes", "--json"])
    assert result.exit_code == 0
    fake.stop.assert_called_once()
    fake.remove.assert_called_once()


def test_db_down_missing_container_is_noop(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.side_effect = _NotFound("absent")
    result = runner.invoke(app, ["db", "mysql", "down", "--yes", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["action"] == "missing"


# ─── shell ──────────────────────────────────────────────────────────────


def test_db_shell_unsupported_engine_errors(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.return_value = _container_mock(name="shimkit-db-phpmyadmin-dev")
    result = runner.invoke(app, ["db", "phpmyadmin", "shell"])
    assert result.exit_code == 1
    assert "does not have a shell" in result.stdout


def test_db_shell_missing_container_errors(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.side_effect = _NotFound("absent")
    result = runner.invoke(app, ["db", "mysql", "shell"])
    assert result.exit_code == 1


def test_db_shell_calls_command_runner_with_docker_exec(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.return_value = _container_mock(name="shimkit-db-mysql-dev")
    captured: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        captured.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr("shimkit.core.command.CommandRunner.run", staticmethod(fake_run))
    result = runner.invoke(app, ["db", "mysql", "shell", "--password", "pw"])
    assert result.exit_code == 0
    assert captured[0][:4] == ["docker", "exec", "-it", "shimkit-db-mysql-dev"]
    assert "-ppw" in captured[0]


# ─── dump ───────────────────────────────────────────────────────────────


def test_db_dump_writes_to_stdout(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    fake = _container_mock(name="shimkit-db-mysql-dev")
    fake.exec_run.return_value = (0, (b"-- DUMP --\n", b""))
    client.containers.get.return_value = fake
    result = runner.invoke(app, ["db", "mysql", "dump"])
    assert result.exit_code == 0
    assert "DUMP" in result.stdout


def test_db_dump_writes_to_file(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    fake = _container_mock(name="shimkit-db-mysql-dev")
    fake.exec_run.return_value = (0, (b"-- big dump --\n", b""))
    client.containers.get.return_value = fake
    out = tmp_path / "dump.sql"
    result = runner.invoke(app, ["db", "mysql", "dump", "--out", str(out), "--json"])
    assert result.exit_code == 0
    assert "-- big dump --" in out.read_text()


def test_db_dump_phpmyadmin_refuses(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.return_value = _container_mock(name="shimkit-db-phpmyadmin-dev")
    result = runner.invoke(app, ["db", "phpmyadmin", "dump"])
    assert result.exit_code == 1


# ─── reset (SEVERE) ─────────────────────────────────────────────────────


def test_db_reset_refuses_without_severe_token(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_version_preflight(monkeypatch)
    _stub_docker_env(monkeypatch)
    result = runner.invoke(app, ["db", "mysql", "reset"])
    assert result.exit_code == 1
    assert "RESET-DB" in result.stdout


def test_db_reset_with_severe_token_proceeds(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    fake = _container_mock(name="shimkit-db-mysql-dev")
    client.containers.get.return_value = fake
    monkeypatch.setenv("HOME", str(tmp_path))
    # Lay a volume so remove_volume has something to delete.
    vol = tmp_path / ".shimkit" / "data" / "db" / "mysql-dev"
    vol.mkdir(parents=True)
    (vol / "file").write_text("data")
    result = runner.invoke(app, ["db", "mysql", "reset", "--confirm", "RESET-DB"])
    assert result.exit_code == 0
    fake.remove.assert_called_once_with(force=True)
    assert not vol.exists()


def test_db_reset_dry_run_does_nothing(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    result = runner.invoke(app, ["db", "mysql", "reset", "--dry-run"])
    # No confirm needed in dry-run.
    assert result.exit_code == 0
    client.containers.get.assert_not_called()


# ─── status / ls ────────────────────────────────────────────────────────


def test_db_status_missing_container(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.side_effect = _NotFound("absent")
    result = runner.invoke(app, ["db", "mysql", "status", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["state"] == "missing"


def test_db_status_running(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.return_value = _container_mock(
        name="shimkit-db-mysql-dev",
        status="running",
        ports={"3306/tcp": [{"HostIp": "127.0.0.1", "HostPort": "13306"}]},
    )
    result = runner.invoke(app, ["db", "mysql", "status", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["state"] == "running"
    assert doc["data"]["host_port"] == 13306
    assert doc["data"]["bind_host"] == "127.0.0.1"


def test_db_ls_empty_when_no_managed_containers(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.list.return_value = []
    result = runner.invoke(app, ["db", "ls", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["containers"] == []


def test_db_ls_lists_shimkit_db_labelled_containers(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.list.return_value = [
        _container_mock(name="shimkit-db-mysql-dev"),
        _container_mock(name="shimkit-db-postgres-qa", image_tag="postgres:16"),
    ]
    result = runner.invoke(app, ["db", "ls", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    names = {c["container_name"] for c in doc["data"]["containers"]}
    assert names == {"shimkit-db-mysql-dev", "shimkit-db-postgres-qa"}


def test_db_ls_passes_scope_filter(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.list.return_value = []
    runner.invoke(app, ["db", "ls", "--json"])
    _, kw = client.containers.list.call_args
    assert kw["filters"] == {"label": ["shimkit.tool=db"]}
