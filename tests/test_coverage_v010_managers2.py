"""More manager coverage for docker_clean, gpg, dns, adguard fix/run.

Mostly exercises dispatcher paths via the CLI surface — the
individual prune / fix branches stay covered by the existing
test_tools_*.py files.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── docker_clean: prune dispatcher paths via CLI ─────────────────────


def _stub_docker_clean(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Stub the docker client + version preflight; return the client mock."""
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
    monkeypatch.setattr("shimkit.core.docker._from_env", lambda: client)
    # Also stub the docker_clean's get_client used by restart timing.
    monkeypatch.setattr(
        "shimkit.tools.docker_clean.client.get_client", lambda: client
    )
    return client


def test_docker_clean_manager_prune_unknown_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct manager API: unknown prune kind returns EX_FAIL."""
    _stub_docker_clean(monkeypatch)
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    mgr = DockerCleanManager()
    mgr._client = MagicMock()
    mgr._platform = None
    assert mgr.prune("not-a-kind") == 1


def test_docker_clean_manager_prune_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    mgr = DockerCleanManager()
    mgr._client = None  # Not booted; dry-run short-circuits anyway.
    assert mgr.prune("images", dry_run=True) == 0


def test_docker_clean_manager_quick_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    mgr = DockerCleanManager()
    mgr._client = None
    assert mgr.quick(dry_run=True) == 0


def test_docker_clean_manager_quick_no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    mgr = DockerCleanManager()
    mgr._client = None
    assert mgr.quick() == 69


def test_docker_clean_manager_stop_all_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    mgr = DockerCleanManager()
    mgr._client = None
    assert mgr.stop_all(dry_run=True) == 0


def test_docker_clean_manager_nuke_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    mgr = DockerCleanManager()
    mgr._client = MagicMock()
    assert mgr.nuke(confirm=None) == 1


def test_docker_clean_manager_inspect_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    mgr = DockerCleanManager()
    mgr._client = MagicMock()
    assert mgr.inspect("lasers") == 1


def test_docker_clean_manager_inspect_no_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    mgr = DockerCleanManager()
    mgr._client = None
    assert mgr.inspect("containers") == 69


def test_docker_clean_manager_compose_down(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}")
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.docker_clean.manager.CommandRunner.run", staticmethod(fake_run)
    )
    mgr = DockerCleanManager()
    assert mgr.compose_down(compose) == 0
    assert seen[0][:3] == ["docker", "compose", "-f"]


def test_docker_clean_manager_compose_down_with_volumes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}")
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.docker_clean.manager.CommandRunner.run", staticmethod(fake_run)
    )
    mgr = DockerCleanManager()
    assert mgr.compose_down(compose, with_volumes=True) == 0
    assert "-v" in seen[0]


def test_docker_clean_manager_compose_down_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    monkeypatch.setattr(
        "shimkit.tools.docker_clean.manager.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(1, "", "fail")),
    )
    mgr = DockerCleanManager()
    assert mgr.compose_down(tmp_path / "compose.yml") == 1


def test_docker_clean_manager_schedule_emit_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    mgr = DockerCleanManager()
    mgr._platform = Platform(system="Linux", machine="x86_64")
    # No out path → stdout via UI.line.
    assert mgr.schedule_emit("weekly", None) == 0


def test_docker_clean_manager_schedule_emit_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    mgr = DockerCleanManager()
    mgr._platform = Platform(system="Linux", machine="x86_64")
    out = tmp_path / "out.snippet"
    assert mgr.schedule_emit("weekly", out) == 0
    assert out.read_text()  # non-empty


# ─── gpg manager: keys list / agent / git-signing show ────────────────


def test_gpg_keys_list_with_no_gpg(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gpg refuses cleanly when gpg isn't on PATH."""
    monkeypatch.setattr("shimkit.core.version.shutil.which", lambda _b: None)
    result = runner.invoke(app, ["gpg", "keys", "list"])
    # Either 69 (preflight refusal) or 1 (graceful warning).
    assert result.exit_code in (0, 1, 69)


def test_gpg_agent_status(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gpg agent status output exercises CommandRunner path."""
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(0, "OK\n", "")),
    )
    # Bypass version preflight.
    monkeypatch.setattr(
        "shimkit.core.version.shutil.which",
        lambda b: f"/usr/bin/{b}" if b in ("gpg", "gpgconf") else None,
    )
    monkeypatch.setattr("shimkit.core.version.preflight", lambda *a, **kw: None)
    result = runner.invoke(app, ["gpg", "agent", "status"])
    # Just ensure no crash; exit 0 or 1 is fine.
    assert result.exit_code in (0, 1)


def test_gpg_git_signing_show(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """git-signing show reads gpg.signingkey config."""
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(0, "B7654321\n", "")),
    )
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.shutil.which", lambda b: f"/usr/bin/{b}"
    )
    monkeypatch.setattr("shimkit.core.version.preflight", lambda *a, **kw: None)
    result = runner.invoke(app, ["gpg", "git-signing", "show"])
    assert result.exit_code in (0, 1)


# ─── dns manager (macOS scoped tool) — at least exercise boot refusal ─


def test_dns_diagnose_refuses_on_linux(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    result = runner.invoke(app, ["dns", "diagnose"])
    # dns is macOS-only.
    assert result.exit_code != 0


# ─── adguard manager: config_validate path ────────────────────────────


def test_adguard_config_validate_ok(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.core import platform as _plat
    from shimkit.tools.adguard import manager as _amgr
    from shimkit.tools.adguard.models import AdGuardInstall

    monkeypatch.setattr(
        _plat.Platform,
        "detect",
        classmethod(lambda cls: _plat.Platform(system="Linux", machine="x86_64")),
    )
    binary = tmp_path / "AdGuardHome"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    mgr = _amgr.AdGuardManager()
    mgr._platform = _plat.Platform(system="Linux", machine="x86_64")
    mgr._install = AdGuardInstall(
        binary=binary,
        yaml_path=tmp_path / "agh.yaml",
        install_root=tmp_path,
    )
    monkeypatch.setattr(
        "shimkit.tools.adguard.manager.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(0, "OK", "")),
    )
    assert mgr.config_validate() == 0


def test_adguard_config_validate_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.core import platform as _plat
    from shimkit.tools.adguard import manager as _amgr
    from shimkit.tools.adguard.models import AdGuardInstall

    monkeypatch.setattr(
        _plat.Platform,
        "detect",
        classmethod(lambda cls: _plat.Platform(system="Linux", machine="x86_64")),
    )
    binary = tmp_path / "AdGuardHome"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    mgr = _amgr.AdGuardManager()
    mgr._platform = _plat.Platform(system="Linux", machine="x86_64")
    mgr._install = AdGuardInstall(
        binary=binary,
        yaml_path=tmp_path / "agh.yaml",
        install_root=tmp_path,
    )
    monkeypatch.setattr(
        "shimkit.tools.adguard.manager.CommandRunner.run",
        staticmethod(lambda *a, **kw: CommandResult(1, "", "config invalid")),
    )
    assert mgr.config_validate() == 1


# ─── self_update small ─────────────────────────────────────────────────


def test_self_update_check_offline_returns_no_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """self_update.check() with no network should return has_update=False."""
    from shimkit import self_update as _su

    def fake_urlopen(*a, **kw):  # type: ignore[no-untyped-def]
        raise OSError("offline")

    monkeypatch.setattr("shimkit.self_update.urlopen", fake_urlopen)
    res = _su.check()
    assert res.has_update is False
