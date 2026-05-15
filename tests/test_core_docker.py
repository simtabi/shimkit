"""Tests for ``shimkit.core.docker``.

The docker-py SDK boundary is mocked at ``shimkit.core.docker._from_env``;
no real daemon access happens. Each test provides a fake client
with just the surface area the manager calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from shimkit.core.docker import (
    DockerEnv,
    DockerNotAvailableError,
    ExecOutcome,
    _scope_from,
)


class _NotFound(Exception):  # noqa: N818 — name mirrors docker.errors.NotFound which we substitute
    """Stand-in for docker.errors.NotFound. Caught by name in find()."""


@pytest.fixture(autouse=True)
def _stub_docker_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject a fake docker.errors.NotFound into sys.modules so
    `from docker.errors import NotFound` succeeds without the real
    docker package being imported.
    """
    import sys
    import types

    if "docker" not in sys.modules:
        docker_mod = types.ModuleType("docker")
        sys.modules["docker"] = docker_mod
    docker_errors = types.ModuleType("docker.errors")
    docker_errors.NotFound = _NotFound  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "docker.errors", docker_errors)


def _stub_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace _from_env so DockerEnv.boot() returns the given mock client."""
    client = MagicMock()
    monkeypatch.setattr(
        "shimkit.core.docker._from_env",
        lambda: client,
    )
    return client


# ─── naming conventions ─────────────────────────────────────────────────


def test_container_name_default_id() -> None:
    assert DockerEnv.container_name("db", "mysql") == "shimkit-db-mysql-dev"


def test_container_name_custom_id() -> None:
    assert DockerEnv.container_name("stack", "lemp", "feature-x") == "shimkit-stack-lemp-feature-x"


def test_volume_path_under_home_data_root() -> None:
    p = DockerEnv.volume_path("mysql")
    assert p.parent == Path.home() / ".shimkit" / "data" / "db"
    assert p.name == "mysql-dev"


def test_volume_path_with_custom_id() -> None:
    assert (
        DockerEnv.volume_path("postgres", "feature-x").name == "postgres-feature-x"
    )


def test_scope_from_name() -> None:
    assert _scope_from("shimkit-db-mysql-dev") == "db"
    assert _scope_from("shimkit-stack-lemp-myproj") == "stack"
    assert _scope_from("non-shimkit-thing") == ""


# ─── boot ──────────────────────────────────────────────────────────────


def test_boot_exits_69_when_sdk_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_unavailable() -> Any:
        raise DockerNotAvailableError("docker-py is not installed.")

    monkeypatch.setattr("shimkit.core.docker._from_env", raise_unavailable)
    with pytest.raises(SystemExit) as exc:
        DockerEnv.create().boot()
    assert exc.value.code == 69


def test_boot_exits_69_when_daemon_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_unavailable() -> Any:
        raise DockerNotAvailableError("Docker daemon is not reachable.")

    monkeypatch.setattr("shimkit.core.docker._from_env", raise_unavailable)
    with pytest.raises(SystemExit) as exc:
        DockerEnv.create().boot()
    assert exc.value.code == 69


def test_boot_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_from_env() -> MagicMock:
        calls["n"] += 1
        return MagicMock()

    monkeypatch.setattr("shimkit.core.docker._from_env", fake_from_env)
    env = DockerEnv.create().boot().boot().boot()
    assert calls["n"] == 1
    assert env.client is not None


# ─── find / run / start / stop / remove ─────────────────────────────────


def test_find_returns_none_for_missing_container(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    client.containers.get.side_effect = _NotFound("missing")
    env = DockerEnv.create().boot()
    assert env.find("absent") is None


def test_find_returns_container_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    fake_container = MagicMock(status="running")
    client.containers.get.return_value = fake_container
    env = DockerEnv.create().boot()
    assert env.find("present") is fake_container


def test_run_invokes_sdk_with_shimkit_label(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    env = DockerEnv.create().boot()
    env.run(
        "mysql:8.0",
        name="shimkit-db-mysql-dev",
        env={"MYSQL_ROOT_PASSWORD": "secret"},
        ports={"3306/tcp": 13306},
    )
    client.containers.run.assert_called_once()
    _, kw = client.containers.run.call_args
    assert kw["name"] == "shimkit-db-mysql-dev"
    assert kw["detach"] is True
    assert kw["environment"] == {"MYSQL_ROOT_PASSWORD": "secret"}
    assert kw["ports"] == {"3306/tcp": 13306}
    # Auto-applied label maps to the scope inferred from the name.
    assert kw["labels"]["shimkit.tool"] == "db"


def test_start_returns_false_for_missing_container(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    client.containers.get.side_effect = _NotFound("missing")
    assert DockerEnv.create().boot().start("absent") is False


def test_start_calls_start_on_existing_container(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    fake = MagicMock()
    client.containers.get.return_value = fake
    DockerEnv.create().boot().start("present")
    fake.start.assert_called_once_with()


def test_stop_returns_false_for_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    client.containers.get.side_effect = _NotFound("missing")
    assert DockerEnv.create().boot().stop("absent") is False


def test_stop_calls_stop_with_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    fake = MagicMock()
    client.containers.get.return_value = fake
    DockerEnv.create().boot().stop("c", timeout=20)
    fake.stop.assert_called_once_with(timeout=20)


def test_remove_returns_false_for_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    client.containers.get.side_effect = _NotFound("missing")
    assert DockerEnv.create().boot().remove("absent") is False


def test_remove_calls_remove_with_force(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    fake = MagicMock()
    client.containers.get.return_value = fake
    DockerEnv.create().boot().remove("c", force=True)
    fake.remove.assert_called_once_with(force=True)


# ─── exec ──────────────────────────────────────────────────────────────


def test_exec_returns_125_for_missing_container(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    client.containers.get.side_effect = _NotFound("missing")
    outcome = DockerEnv.create().boot().exec("absent", ["echo", "hi"])
    assert outcome.exit_code == 125
    assert "no such container" in outcome.stderr


def test_exec_parses_demuxed_output(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    fake = MagicMock()
    fake.exec_run.return_value = (0, (b"hello\n", b""))
    client.containers.get.return_value = fake
    outcome = DockerEnv.create().boot().exec("c", ["echo", "hello"])
    assert outcome.exit_code == 0
    assert outcome.stdout == "hello\n"
    assert outcome.ok is True


def test_exec_handles_non_tuple_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Some docker-py versions return bytes (not tuple) for demux=True
    on certain commands. The wrapper should still produce an
    ExecOutcome."""
    client = _stub_client(monkeypatch)
    fake = MagicMock()
    fake.exec_run.return_value = (0, b"raw bytes\n")
    client.containers.get.return_value = fake
    outcome = DockerEnv.create().boot().exec("c", ["echo", "hi"])
    assert outcome.stdout == "raw bytes\n"
    assert outcome.stderr == ""


# ─── logs / list_managed ────────────────────────────────────────────────


def test_logs_returns_none_for_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    client.containers.get.side_effect = _NotFound("missing")
    assert DockerEnv.create().boot().logs("absent") is None


def test_logs_passes_through_follow_and_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    fake = MagicMock()
    fake.logs.return_value = b"log body"
    client.containers.get.return_value = fake
    DockerEnv.create().boot().logs("c", follow=True, tail=50)
    fake.logs.assert_called_once_with(stream=True, follow=True, tail=50)


def test_list_managed_filters_to_shimkit_label(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    client.containers.list.return_value = []
    DockerEnv.create().boot().list_managed()
    _, kw = client.containers.list.call_args
    assert kw["all"] is True
    assert kw["filters"] == {"label": ["shimkit.tool"]}


def test_list_managed_narrows_to_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _stub_client(monkeypatch)
    client.containers.list.return_value = []
    DockerEnv.create().boot().list_managed(scope="db")
    _, kw = client.containers.list.call_args
    assert kw["filters"] == {"label": ["shimkit.tool=db"]}


# ─── remove_volume ──────────────────────────────────────────────────────


def test_remove_volume_refuses_paths_outside_shimkit_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_client(monkeypatch)
    env = DockerEnv.create().boot()
    stray = tmp_path / "not-shimkit-data"
    stray.mkdir()
    # Refuse to delete: tmp_path is NOT under ~/.shimkit/data
    assert env.remove_volume(stray) is False
    assert stray.exists()


def test_remove_volume_returns_false_for_missing_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_client(monkeypatch)
    env = DockerEnv.create().boot()
    # Point HOME at tmp so the safety predicate passes, but the path
    # itself doesn't exist.
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / ".shimkit" / "data" / "db" / "mysql-dev"
    assert env.remove_volume(target) is False


def test_remove_volume_deletes_path_under_data_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_client(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / ".shimkit" / "data" / "db" / "mysql-dev"
    target.mkdir(parents=True)
    (target / "file.bin").write_text("data")
    env = DockerEnv.create().boot()
    assert env.remove_volume(target) is True
    assert not target.exists()


# ─── ExecOutcome ────────────────────────────────────────────────────────


def test_exec_outcome_ok_property() -> None:
    assert ExecOutcome(0, "", "").ok is True
    assert ExecOutcome(1, "", "boom").ok is False
