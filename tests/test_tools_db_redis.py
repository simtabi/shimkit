"""Tests for the v0.15.0 Redis engine driver and its plumbing
through the db manager.

The shared up/down/status/shell tests live in test_tools_db.py; this
file covers Redis-specific behaviour:

- environment_for_up returns {} (Redis uses CLI args, not env vars)
- up_command sets --requirepass + --appendonly yes
- shell_argv uses redis-cli with -a + --no-auth-warning
- supports_dump is False
- supports_on_host is False
- manager wires up_command through `docker run`
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.tools.db import engines as _engines
from shimkit.tools.db.engines.redis import Redis


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── registry ───────────────────────────────────────────────────────────


def test_redis_in_registry() -> None:
    assert "redis" in _engines.REGISTRY
    assert isinstance(_engines.get("redis"), Redis)


def test_registry_order_stable() -> None:
    """Insertion order is preserved: phpmyadmin still last."""
    names = list(_engines.REGISTRY)
    assert names == ["mysql", "mariadb", "postgres", "mongo", "redis", "phpmyadmin"]


# ─── pure engine driver ───────────────────────────────────────────────


def test_redis_environment_for_up_is_empty() -> None:
    """Redis ignores env vars — the official image doesn't read
    REDIS_PASSWORD. AUTH happens via up_command."""
    eng = Redis()
    assert eng.environment_for_up(password="shimkit-dev") == {}


def test_redis_up_command_sets_requirepass_and_aof() -> None:
    eng = Redis()
    argv = eng.up_command(password="topsecret")
    assert argv[0] == "redis-server"
    assert "--requirepass" in argv
    idx = argv.index("--requirepass")
    assert argv[idx + 1] == "topsecret"
    # AOF persistence is the recommended dev posture.
    assert "--appendonly" in argv
    aof_idx = argv.index("--appendonly")
    assert argv[aof_idx + 1] == "yes"


def test_redis_shell_argv_uses_no_auth_warning() -> None:
    eng = Redis()
    argv = eng.shell_argv(password="topsecret")
    assert argv[0] == "redis-cli"
    assert "-a" in argv
    assert "topsecret" in argv
    # Suppresses the noisy `-a` warning on stderr.
    assert "--no-auth-warning" in argv


def test_redis_shell_argv_no_password() -> None:
    eng = Redis()
    # With an empty password — defensive path, shouldn't happen in
    # practice (we always pass shimkit-dev).
    argv = eng.shell_argv(password="")
    assert argv == ["redis-cli"]


def test_redis_supports_shell() -> None:
    assert Redis().supports_shell() is True


def test_redis_supports_dump_is_false() -> None:
    """Redis backups are volume-level, not logical dumps."""
    assert Redis().supports_dump() is False


def test_redis_supports_on_host_is_false() -> None:
    """shimkit doesn't manage host-installed Redis services."""
    assert Redis().supports_on_host() is False


def test_redis_data_dir_is_data() -> None:
    assert Redis().data_dir() == "/data"


def test_redis_container_port_is_6379() -> None:
    assert Redis().container_port == 6379


def test_redis_name_is_redis() -> None:
    assert Redis().name == "redis"


# ─── manager: up_command wired through docker run ────────────────────


def test_db_redis_up_passes_command_to_docker_run(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """The manager wires Engine.up_command through `docker run`. Mock
    DockerEnv.run and assert command kwarg present + shape."""
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.core.version.preflight", lambda *a, **kw: None)

    # Stub docker.errors before importing DockerEnv.
    import sys as _sys
    import types

    fake = types.ModuleType("docker.errors")

    class _NotFound(Exception):  # noqa: N818
        pass

    fake.NotFound = _NotFound  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "docker.errors", fake)

    captured: dict[str, Any] = {}

    class _FakeClient:
        @property
        def containers(self):
            class _C:
                @staticmethod
                def get(name: str):
                    raise _NotFound

                @staticmethod
                def run(image: str, **kwargs: object) -> MagicMock:
                    captured["image"] = image
                    captured.update(kwargs)
                    return MagicMock()

                @staticmethod
                def list(**_: object) -> list[MagicMock]:
                    return []

            return _C()

        @property
        def networks(self):
            class _N:
                @staticmethod
                def get(name: str) -> MagicMock:
                    raise _NotFound

                @staticmethod
                def create(*a, **kw) -> MagicMock:
                    return MagicMock()

            return _N()

        @staticmethod
        def ping() -> bool:
            return True

    monkeypatch.setattr("shimkit.core.docker._from_env", lambda: _FakeClient())

    result = runner.invoke(
        app,
        ["db", "redis", "up", "--yes", "--password", "topsecret"],
    )
    assert result.exit_code == 0, result.stdout
    # The `command=` kwarg was passed through.
    assert "command" in captured
    cmd = captured["command"]
    assert cmd[0] == "redis-server"
    assert "--requirepass" in cmd
    assert "topsecret" in cmd


def test_db_redis_dump_refused(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """`db redis dump` should refuse with the unsupported-operation
    error from the engine driver."""
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.core.version.preflight", lambda *a, **kw: None)
    import sys as _sys
    import types

    fake = types.ModuleType("docker.errors")

    class _NotFound(Exception):  # noqa: N818
        pass

    fake.NotFound = _NotFound  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "docker.errors", fake)
    container = MagicMock()
    container.status = "running"
    client = MagicMock()
    client.containers.get.return_value = container
    monkeypatch.setattr("shimkit.core.docker._from_env", lambda: client)

    result = runner.invoke(app, ["db", "redis", "dump"])
    # supports_dump=False → exit 1 with the message.
    assert result.exit_code == 1
    assert "dump" in result.output.lower()


def test_db_redis_on_host_refused(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """`db redis up --on-host` is not supported."""
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )

    class _Host:
        @classmethod
        def detect(cls, platform=None):  # type: ignore[no-untyped-def]
            return cls()

    monkeypatch.setattr("shimkit.tools.db.manager.HostService", _Host)
    result = runner.invoke(app, ["db", "redis", "up", "--yes", "--on-host"])
    assert result.exit_code == 1
    assert "on-host" in result.output.lower() or "--on-host" in result.output.lower()


# ─── config ──────────────────────────────────────────────────────────


def test_redis_in_config_defaults() -> None:
    from shimkit.config import get_config

    cfg = get_config().tools.db
    assert "redis" in cfg.engines
    assert cfg.engines["redis"].image == "redis:7-alpine"
    assert cfg.engines["redis"].default_port == 16379
