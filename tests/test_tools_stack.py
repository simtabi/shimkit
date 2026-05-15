"""Tests for ``shimkit stack`` (LEMP recipe today).

DockerEnv is mocked end-to-end; the recipe's idempotency, naming,
nginx-config templating, and lifecycle are exercised against fake
container objects.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.tools.stack import lemp


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
    client = MagicMock()
    monkeypatch.setattr("shimkit.core.docker._from_env", lambda: client)
    return client


def _bypass_version_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "shimkit.core.version.preflight",
        lambda tools, force=False, runner=None: None,
    )


def _container_mock(*, name: str, status: str = "running") -> MagicMock:
    c = MagicMock()
    c.name = name
    c.status = status
    parts = name.split("-")
    # Best-effort: works for "shimkit-stack-lemp-<project>-<role>" inputs.
    project = parts[3] if len(parts) >= 5 else name
    role = parts[-1] if len(parts) >= 2 else "unknown"
    c.labels = {
        "shimkit.tool": "stack",
        "shimkit.stack": "lemp",
        "shimkit.project": project,
        "shimkit.role": role,
    }
    return c


# ─── nginx-config template ─────────────────────────────────────────────


def test_nginx_conf_includes_php_host() -> None:
    conf = lemp.render_nginx_conf(php_host="shimkit-stack-lemp-myproj-php")
    assert "shimkit-stack-lemp-myproj-php:9000" in conf
    assert "root /srv/app;" in conf
    assert "try_files $uri" in conf


def test_nginx_conf_has_security_headers() -> None:
    conf = lemp.render_nginx_conf(php_host="x")
    assert "server_tokens off;" in conf
    assert "X-Frame-Options" in conf


# ─── naming ────────────────────────────────────────────────────────────


def test_network_and_container_naming() -> None:
    assert lemp._network_name("myproj") == "shimkit-stack-lemp-myproj-net"
    assert lemp._container_name("myproj", "db") == "shimkit-stack-lemp-myproj-db"
    assert lemp._container_name("myproj", "nginx") == "shimkit-stack-lemp-myproj-nginx"


def test_safe_password_env_for_mysql() -> None:
    env = lemp._safe_password_env("mysql", "secret")
    assert env["MYSQL_ROOT_PASSWORD"] == "secret"


def test_safe_password_env_unknown_engine_raises() -> None:
    with pytest.raises(ValueError, match="Unknown db engine"):
        lemp._safe_password_env("redis", "x")


# ─── boot ──────────────────────────────────────────────────────────────


def test_boot_exits_69_when_docker_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.core.docker._from_env", lambda: MagicMock())
    monkeypatch.setattr("shimkit.core.version.shutil.which", lambda _b: None)
    from shimkit.tools.stack.manager import StackManager

    with pytest.raises(SystemExit) as exc:
        StackManager.create().boot()
    assert exc.value.code == 69


# ─── up ────────────────────────────────────────────────────────────────


def test_lemp_up_creates_three_containers_and_network(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.side_effect = _NotFound("absent")
    client.networks.get.side_effect = _NotFound("absent")

    result = runner.invoke(
        app,
        [
            "stack",
            "lemp",
            "up",
            "--yes",
            "--project",
            "myproj",
            "--project-root",
            str(tmp_path),
            "--password",
            "test-pw",
            "--json",
        ],
    )
    assert result.exit_code == 0
    # Network created.
    client.networks.create.assert_called_once()
    net_args, _ = client.networks.create.call_args
    assert net_args[0] == "shimkit-stack-lemp-myproj-net"
    # Three containers created.
    assert client.containers.run.call_count == 3
    names_created = [call.kwargs["name"] for call in client.containers.run.call_args_list]
    assert names_created == [
        "shimkit-stack-lemp-myproj-db",
        "shimkit-stack-lemp-myproj-php",
        "shimkit-stack-lemp-myproj-nginx",
    ]
    # nginx's volumes include the bind-mounted project + the nginx conf.
    nginx_kw = client.containers.run.call_args_list[-1].kwargs
    assert any(v["bind"] == "/srv/app" for v in nginx_kw["volumes"].values())
    assert any(v["bind"] == "/etc/nginx/conf.d/default.conf" for v in nginx_kw["volumes"].values())
    # nginx port binding on host.
    binding = nginx_kw["ports"]["80/tcp"]
    assert binding == ("127.0.0.1", 18080)


def test_lemp_up_already_running_is_noop(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    # All three exist and are running.
    client.networks.get.return_value = MagicMock()
    client.containers.get.side_effect = [
        _container_mock(name="shimkit-stack-lemp-shimkit-dev-db"),
        _container_mock(name="shimkit-stack-lemp-shimkit-dev-php"),
        _container_mock(name="shimkit-stack-lemp-shimkit-dev-nginx"),
    ]
    result = runner.invoke(
        app,
        [
            "stack",
            "lemp",
            "up",
            "--yes",
            "--project-root",
            str(tmp_path),
            "--json",
        ],
    )
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["actions"] == {
        "db": "already_running",
        "php": "already_running",
        "nginx": "already_running",
    }
    client.containers.run.assert_not_called()


def test_lemp_up_dry_run_does_not_invoke_docker(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    result = runner.invoke(
        app,
        [
            "stack",
            "lemp",
            "up",
            "--yes",
            "--dry-run",
            "--project-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    client.networks.create.assert_not_called()
    client.containers.run.assert_not_called()


def test_lemp_up_refuses_under_no_input(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _bypass_version_preflight(monkeypatch)
    _stub_docker_env(monkeypatch)
    result = runner.invoke(
        app,
        ["stack", "--no-input", "lemp", "up", "--project-root", str(tmp_path)],
    )
    assert result.exit_code == 1


def test_lemp_up_unknown_engine_errors(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _bypass_version_preflight(monkeypatch)
    _stub_docker_env(monkeypatch)
    result = runner.invoke(
        app,
        [
            "stack",
            "lemp",
            "up",
            "--yes",
            "--db",
            "redis",
            "--project-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1


def test_lemp_up_passes_db_engine_image_through(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.side_effect = _NotFound("absent")
    client.networks.get.side_effect = _NotFound("absent")
    result = runner.invoke(
        app,
        [
            "stack",
            "lemp",
            "up",
            "--yes",
            "--db",
            "postgres",
            "--project-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    # First container is the db; image should be postgres:16 (default).
    db_call = client.containers.run.call_args_list[0]
    assert db_call.args[0] == "postgres:16"
    assert db_call.kwargs["environment"]["POSTGRES_PASSWORD"] == "shimkit-dev"


# ─── down ──────────────────────────────────────────────────────────────


def test_lemp_down_removes_all(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    fake = MagicMock()
    fake.name = "x"
    fake.status = "running"
    # find() succeeds for all three; network exists.
    client.containers.get.return_value = fake
    client.networks.get.return_value = MagicMock()
    result = runner.invoke(app, ["stack", "lemp", "down", "--yes", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["actions"]["db"] == "removed"
    assert doc["data"]["actions"]["network"] == "removed"


def test_lemp_down_missing_is_clean(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.side_effect = _NotFound("absent")
    client.networks.get.side_effect = _NotFound("absent")
    result = runner.invoke(app, ["stack", "lemp", "down", "--yes", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    actions = doc["data"]["actions"]
    assert actions["db"] == "missing"
    assert actions["network"] == "missing"


# ─── status ────────────────────────────────────────────────────────────


def test_lemp_status_reports_running_state(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.side_effect = [
        _container_mock(name="db", status="running"),
        _container_mock(name="php", status="running"),
        _container_mock(name="nginx", status="running"),
    ]
    result = runner.invoke(app, ["stack", "lemp", "status", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["all_running"] is True
    assert doc["data"]["db"] == "running"


def test_lemp_status_reports_missing(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.get.side_effect = _NotFound("absent")
    result = runner.invoke(app, ["stack", "lemp", "status", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["all_running"] is False
    assert doc["data"]["db"] == "missing"


# ─── ls (across projects) ──────────────────────────────────────────────


def test_stack_ls_groups_by_project(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.list.return_value = [
        _container_mock(name="shimkit-stack-lemp-alpha-db"),
        _container_mock(name="shimkit-stack-lemp-alpha-php"),
        _container_mock(name="shimkit-stack-lemp-alpha-nginx"),
        _container_mock(name="shimkit-stack-lemp-beta-db"),
    ]
    result = runner.invoke(app, ["stack", "ls", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    projects = {p["project"]: p["roles"] for p in doc["data"]["projects"]}
    assert "alpha" in projects and "beta" in projects
    assert set(projects["alpha"]) == {"db", "php", "nginx"}


def test_stack_ls_empty(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    client.containers.list.return_value = []
    result = runner.invoke(app, ["stack", "ls", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["projects"] == []


# ─── exec ──────────────────────────────────────────────────────────────


def test_lemp_exec_runs_in_php_container(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    fake = MagicMock()
    fake.exec_run.return_value = (0, (b"ok\n", b""))
    client.containers.get.return_value = fake
    result = runner.invoke(
        app,
        ["stack", "lemp", "exec", "--project", "myproj", "--", "php", "-v"],
    )
    assert result.exit_code == 0
    assert "ok" in result.stdout
    # Verify the container looked up was the php container, not db/nginx.
    assert any(
        call.args[0] == "shimkit-stack-lemp-myproj-php"
        for call in client.containers.get.call_args_list
    )


def test_lemp_exec_non_zero_returns_1(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    fake = MagicMock()
    fake.exec_run.return_value = (3, (b"", b"boom"))
    client.containers.get.return_value = fake
    result = runner.invoke(app, ["stack", "lemp", "exec", "--", "false"])
    assert result.exit_code == 1


# ─── logs ──────────────────────────────────────────────────────────────


def test_lemp_logs_emits_for_each_container(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_version_preflight(monkeypatch)
    client = _stub_docker_env(monkeypatch)
    fake = MagicMock()
    fake.logs.return_value = b"some log line\n"
    client.containers.get.return_value = fake
    result = runner.invoke(app, ["stack", "lemp", "logs", "--tail", "10"])
    assert result.exit_code == 0
    # Each role section appears in the output.
    for role in ("nginx", "php", "db"):
        assert role in result.stdout
