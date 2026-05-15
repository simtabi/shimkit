"""Coverage for db manager paths: status output formatting, --on-host
status JSON, dump file write, shell argv with PGPASSWORD, dry-run
branches."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from shimkit.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── status JSON output (one path) ──────────────────────────────────


def test_db_status_running_json(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """status outputs JSON when container is running."""
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
    container.name = "shimkit-db-mysql-dev"
    container.status = "running"
    container.image.tags = ["mysql:8.0"]
    container.ports = {"3306/tcp": [{"HostIp": "127.0.0.1", "HostPort": "13306"}]}
    client = MagicMock()
    client.containers.get.return_value = container
    monkeypatch.setattr("shimkit.core.docker._from_env", lambda: client)
    result = runner.invoke(app, ["db", "mysql", "status", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.output)
    assert doc["data"]["state"] == "running"
    assert doc["data"]["host_port"] == 13306


# ─── dump to file ────────────────────────────────────────────────────


def test_db_dump_to_file(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`db mysql dump --out PATH` writes dump bytes to PATH."""
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

    client = MagicMock()
    container = MagicMock()
    container.name = "shimkit-db-mysql-dev"
    container.status = "running"
    client.containers.get.return_value = container
    # Stub exec_run to return demuxed (stdout, stderr).
    container.exec_run.return_value = (0, (b"-- mysql dump\nUSE app;\n", b""))
    monkeypatch.setattr("shimkit.core.docker._from_env", lambda: client)
    out = tmp_path / "dump.sql"
    result = runner.invoke(
        app, ["db", "mysql", "dump", "--out", str(out), "--json"]
    )
    assert result.exit_code == 0
    assert out.is_file()
    assert "USE app;" in out.read_text()


# ─── _to_status_row helper edge cases ────────────────────────────────


def test_to_status_row_parses_engine_from_name() -> None:
    from shimkit.tools.db.manager import _to_status_row

    container = MagicMock()
    container.name = "shimkit-db-postgres-prod"
    container.status = "running"
    container.image.tags = ["postgres:16"]
    container.ports = {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "15432"}]}
    row = _to_status_row(container)
    assert row.engine == "postgres"
    assert row.image == "postgres:16"
    assert row.host_port == 15432
    assert row.bind_host == "0.0.0.0"


def test_to_status_row_no_ports() -> None:
    from shimkit.tools.db.manager import _to_status_row

    container = MagicMock()
    container.name = "shimkit-db-phpmyadmin-dev"
    container.status = "exited"
    container.image.tags = []
    container.ports = {}
    row = _to_status_row(container)
    assert row.engine == "phpmyadmin"
    assert row.host_port is None


def test_to_status_row_fallback_engine() -> None:
    from shimkit.tools.db.manager import _to_status_row

    container = MagicMock()
    container.name = "weirdly-named-container"
    container.status = "running"
    container.image.tags = []
    container.ports = {}
    row = _to_status_row(container, fallback_engine="zz")
    assert row.engine == "zz"


# ─── _to_status_row malformed ports → falls through gracefully ──────


def test_to_status_row_malformed_ports() -> None:
    from shimkit.tools.db.manager import _to_status_row

    container = MagicMock()
    container.name = "shimkit-db-mysql-dev"
    container.status = "running"
    container.image.tags = ["mysql:8.0"]
    # Missing HostPort value → ValueError on int() — caught.
    container.ports = {"3306/tcp": [{"HostIp": "127.0.0.1", "HostPort": "not-a-port"}]}
    row = _to_status_row(container)
    # Falls back to None when parsing fails.
    assert row.host_port is None


# ─── on-host json output paths ───────────────────────────────────────


def test_db_up_on_host_json_includes_state(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shimkit.core import HostServiceResult
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

        def state(self, service):  # type: ignore[no-untyped-def]
            return "running"

        def start(self, service):  # type: ignore[no-untyped-def]
            return HostServiceResult(ok=True, state="running")

        def stop(self, service):  # type: ignore[no-untyped-def]
            return HostServiceResult(ok=True, state="stopped")

    monkeypatch.setattr("shimkit.tools.db.manager.HostService", _Host)
    monkeypatch.setattr(
        "shimkit.tools.db.manager.shutil.which",
        lambda b: f"/usr/bin/{b}" if b == "mysql" else None,
    )
    result = runner.invoke(
        app, ["db", "mysql", "up", "--yes", "--on-host", "--json"]
    )
    assert result.exit_code == 0
    doc = json.loads(result.output)
    assert doc["data"]["mode"] == "on-host"
    assert doc["data"]["state"] == "running"


def test_db_down_on_host_json(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shimkit.core import HostServiceResult
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

        def state(self, service):  # type: ignore[no-untyped-def]
            return "stopped"

        def stop(self, service):  # type: ignore[no-untyped-def]
            return HostServiceResult(ok=True, state="stopped")

    monkeypatch.setattr("shimkit.tools.db.manager.HostService", _Host)
    monkeypatch.setattr(
        "shimkit.tools.db.manager.shutil.which",
        lambda b: f"/usr/bin/{b}" if b == "mysql" else None,
    )
    result = runner.invoke(
        app, ["db", "mysql", "down", "--yes", "--on-host", "--json"]
    )
    assert result.exit_code == 0
    doc = json.loads(result.output)
    assert doc["data"]["state"] == "stopped"


def test_db_status_on_host_running_via_cli(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover the non-JSON output path for status --on-host."""
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

        def state(self, service):  # type: ignore[no-untyped-def]
            return "running"

    monkeypatch.setattr("shimkit.tools.db.manager.HostService", _Host)
    monkeypatch.setattr(
        "shimkit.tools.db.manager.shutil.which",
        lambda b: f"/usr/bin/{b}" if b == "mysql" else None,
    )
    result = runner.invoke(app, ["db", "mysql", "status", "--on-host"])
    assert result.exit_code == 0
    assert "running" in result.output


def test_db_up_on_host_macos_path(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover the macOS service-name resolution branch."""
    from shimkit.core import HostServiceResult
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Darwin", machine="arm64")),
    )
    seen: list[str] = []

    class _Host:
        @classmethod
        def detect(cls, platform=None):  # type: ignore[no-untyped-def]
            return cls()

        def state(self, service):  # type: ignore[no-untyped-def]
            return "stopped"

        def start(self, service):  # type: ignore[no-untyped-def]
            seen.append(service)
            return HostServiceResult(ok=True, state="running")

    monkeypatch.setattr("shimkit.tools.db.manager.HostService", _Host)
    monkeypatch.setattr(
        "shimkit.tools.db.manager.shutil.which",
        lambda b: f"/usr/bin/{b}" if b == "mysql" else None,
    )
    result = runner.invoke(app, ["db", "mysql", "up", "--yes", "--on-host"])
    assert result.exit_code == 0
    # macOS service name comes from host_services.mysql.service_macos.
    assert seen == ["mysql"]
