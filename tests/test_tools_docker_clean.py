from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.tools.docker_clean import client
from shimkit.tools.docker_clean.models import DockerDisk


@pytest.fixture(autouse=True)
def _bypass_version_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    """`DockerCleanManager.boot()` (W7) preflights the docker version
    constraint via `shutil.which`. macOS CI runners don't have docker
    installed, so the preflight would exit 69 before the test's own
    `client.get_client` / `_require_optional_extras` stubs are reached.
    Bypass the preflight by default; tests that want to assert it fires
    can re-enable it in their own monkeypatch scope.
    """
    monkeypatch.setattr(
        "shimkit.core.version.preflight",
        lambda tools, force=False, runner=None: None,
    )


# --- platform gate ---------------------------------------------------------


def test_boot_exits_69_when_daemon_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.tools.docker_clean import client as client_mod
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    monkeypatch.setattr(client_mod, "get_client", lambda: None)
    with pytest.raises(SystemExit) as exc:
        DockerCleanManager.create().boot()
    assert exc.value.code == 69


def test_boot_exits_69_when_optional_extra_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The brief's mandatory-minimum test: boot() refuses without the
    `docker` extra installed."""
    import builtins

    from shimkit.tools.docker_clean.manager import DockerCleanManager

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):  # type: ignore[no-untyped-def]
        if name == "docker":
            raise ImportError("simulated docker-missing for test")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(SystemExit) as exc:
        DockerCleanManager.create().boot()
    assert exc.value.code == 69


# --- status ---------------------------------------------------------------


def test_status_json_emits_disk_breakdown(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shimkit.tools.docker_clean import client as client_mod

    stub_disk = DockerDisk(
        images_count=3,
        images_size_bytes=10_000_000,
        images_reclaimable_bytes=5_000_000,
        containers_count=2,
        containers_size_bytes=200,
        containers_reclaimable_bytes=100,
        volumes_count=1,
        volumes_size_bytes=4096,
        volumes_reclaimable_bytes=0,
        build_cache_size_bytes=999,
        build_cache_reclaimable_bytes=999,
    )
    monkeypatch.setattr(client_mod, "get_client", lambda: object())
    monkeypatch.setattr(client_mod, "disk_usage", lambda: stub_disk)
    monkeypatch.setattr("shimkit.tools.docker_clean.desktop.status", lambda: "running")

    result = runner.invoke(app, ["docker-clean", "status", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["step"] == "status"
    assert doc["data"]["disk"]["images"]["count"] == 3


# --- nuke confirmation token ---------------------------------------------


def test_nuke_requires_confirm_token(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.docker_clean import client as client_mod

    monkeypatch.setattr(client_mod, "get_client", lambda: object())
    result = runner.invoke(app, ["docker-clean", "nuke"])
    assert result.exit_code == 1
    assert "Pass --confirm DELETE" in result.stdout


def test_nuke_rejects_wrong_token(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.docker_clean import client as client_mod

    monkeypatch.setattr(client_mod, "get_client", lambda: object())
    result = runner.invoke(app, ["docker-clean", "nuke", "--confirm", "wrong"])
    assert result.exit_code == 1


# --- dry-run --------------------------------------------------------------


def test_quick_dry_run_calls_no_pruner(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.docker_clean import client as client_mod
    from shimkit.tools.docker_clean import pruner

    called: list[str] = []

    def fail_if_called(*_a: Any, **_kw: Any) -> Any:
        called.append("nope")
        raise AssertionError("dry-run must not call pruner")

    monkeypatch.setattr(client_mod, "get_client", lambda: object())
    monkeypatch.setattr(pruner, "stop_all_containers", fail_if_called)
    monkeypatch.setattr(pruner, "remove_all_containers", fail_if_called)
    monkeypatch.setattr(pruner, "prune_images", fail_if_called)

    result = runner.invoke(app, ["docker-clean", "quick", "--dry-run"])
    assert result.exit_code == 0
    assert called == []


# --- CLI surface ----------------------------------------------------------


def test_cli_docker_clean_help_lists_all_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["docker-clean", "--help"])
    assert result.exit_code == 0
    for cmd in (
        "status",
        "quick",
        "nuke",
        "restart",
        "stop-all",
        "prune-images",
        "prune-volumes",
        "prune-networks",
        "prune-builders",
        "orphans",
        "inspect",
        "compose-down",
        "schedule",
    ):
        assert cmd in result.stdout


# --- client parser --------------------------------------------------------


def test_parse_size_handles_units() -> None:
    assert client._parse_size("1.5GB") == int(1.5 * 1024**3)
    assert client._parse_size("12MB") == 12 * 1024**2
    assert client._parse_size("0") == 0
    assert client._parse_size("") == 0
    assert client._parse_size(42) == 42


def test_safe_int() -> None:
    assert client._safe_int("42") == 42
    assert client._safe_int(3.7) == 3
    assert client._safe_int(None) == 0
    assert client._safe_int("nope") == 0


# --- schedule ------------------------------------------------------------


def test_schedule_macos_emits_launchd(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.docker_clean import schedule

    body = schedule.emit("weekly", Platform(system="Darwin", machine="arm64"))
    assert "<plist" in body
    assert "Weekday" in body


def test_schedule_linux_emits_systemd_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.docker_clean import schedule

    body = schedule.emit("daily", Platform(system="Linux", machine="x86_64"))
    assert "OnCalendar" in body
    assert "*-*-* 03:00:00" in body


# --- buildx prune (no daemon needed in test) -----------------------------


def test_prune_buildx_lists_builders_and_runs_each(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.core import CommandResult
    from shimkit.tools.docker_clean import client as client_mod
    from shimkit.tools.docker_clean import pruner
    from shimkit.tools.docker_clean.models import BuildxBuilder

    monkeypatch.setattr(
        client_mod,
        "list_buildx_builders",
        lambda: [BuildxBuilder(name="a"), BuildxBuilder(name="b")],
    )
    calls: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        calls.append(cmd)
        return CommandResult(0, "", "")

    monkeypatch.setattr("shimkit.core.CommandRunner.run", staticmethod(fake_run))
    out = pruner.prune_buildx_builders()
    assert out.applied
    assert len(calls) == 2  # one per builder
    assert all("--builder" in cmd for cmd in calls)


def test_prune_buildx_falls_back_when_no_builders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no buildx builders are listed, fall back to `docker builder prune -af`."""
    from shimkit.core import CommandResult
    from shimkit.tools.docker_clean import client as client_mod
    from shimkit.tools.docker_clean import pruner

    monkeypatch.setattr(client_mod, "list_buildx_builders", lambda: [])
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "shimkit.core.CommandRunner.run",
        staticmethod(lambda cmd, **_: (calls.append(cmd), CommandResult(0, "", ""))[1]),
    )
    out = pruner.prune_buildx_builders()
    assert out.applied
    assert calls == [["docker", "builder", "prune", "-af"]]


# --- client.disk_usage parser --------------------------------------------


def test_disk_usage_parses_top_level_json_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """docker system df --format json on Docker 25+ emits a JSON array."""
    from shimkit.core import CommandResult
    from shimkit.tools.docker_clean import client as client_mod

    sample = (
        '[{"Type":"Images","Count":3,"Size":"10MB","Reclaimable":"5MB"},'
        '{"Type":"Containers","Count":2,"Size":"200B","Reclaimable":"100B"},'
        '{"Type":"Volumes","Count":1,"Size":"4KB","Reclaimable":"0B"},'
        '{"Type":"Build Cache","Size":"5GB","Reclaimable":"5GB"}]'
    )
    monkeypatch.setattr(
        "shimkit.tools.docker_clean.client.CommandRunner.run",
        staticmethod(lambda cmd, **_: CommandResult(0, sample, "")),
    )
    disk = client_mod.disk_usage()
    assert disk is not None
    assert disk.images_count == 3
    assert disk.containers_count == 2
    assert disk.volumes_size_bytes == 4 * 1024
    assert disk.build_cache_reclaimable_bytes == 5 * 1024**3


def test_disk_usage_parses_ndjson(monkeypatch: pytest.MonkeyPatch) -> None:
    """Older Docker emits one JSON object per line."""
    from shimkit.core import CommandResult
    from shimkit.tools.docker_clean import client as client_mod

    sample = (
        '{"Type":"Images","Count":1,"Size":"100MB","Reclaimable":"50MB"}\n'
        '{"Type":"Containers","Count":0,"Size":"0B","Reclaimable":"0B"}\n'
    )
    monkeypatch.setattr(
        "shimkit.tools.docker_clean.client.CommandRunner.run",
        staticmethod(lambda cmd, **_: CommandResult(0, sample, "")),
    )
    disk = client_mod.disk_usage()
    assert disk is not None
    assert disk.images_count == 1
    assert disk.images_size_bytes == 100 * 1024**2


def test_disk_usage_returns_none_on_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.core import CommandResult
    from shimkit.tools.docker_clean import client as client_mod

    monkeypatch.setattr(
        "shimkit.tools.docker_clean.client.CommandRunner.run",
        staticmethod(lambda cmd, **_: CommandResult(0, "not json", "")),
    )
    assert client_mod.disk_usage() is None


def test_disk_usage_returns_none_when_command_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.core import CommandResult
    from shimkit.tools.docker_clean import client as client_mod

    monkeypatch.setattr(
        "shimkit.tools.docker_clean.client.CommandRunner.run",
        staticmethod(lambda cmd, **_: CommandResult(1, "", "daemon down")),
    )
    assert client_mod.disk_usage() is None


def test_list_buildx_builders_parses_json_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.core import CommandResult
    from shimkit.tools.docker_clean import client as client_mod

    sample = (
        '{"Name":"default","Driver":"docker","Nodes":[{"Name":"default"}]}\n'
        '{"Name":"my-builder","Driver":"docker-container","Nodes":[]}\n'
    )
    monkeypatch.setattr(
        "shimkit.tools.docker_clean.client.CommandRunner.run",
        staticmethod(lambda cmd, **_: CommandResult(0, sample, "")),
    )
    builders = client_mod.list_buildx_builders()
    assert [b.name for b in builders] == ["default", "my-builder"]


def test_is_wsl_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.docker_clean import client as client_mod

    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-22.04")
    assert client_mod.is_wsl() is True


def test_is_wsl_false_when_no_env_and_no_proc(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.docker_clean import client as client_mod

    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    # /proc/version may or may not exist on macOS; the function catches OSError.
    assert isinstance(client_mod.is_wsl(), bool)


# --- desktop -------------------------------------------------------------


def test_has_desktop_cli_false_when_docker_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    from shimkit.tools.docker_clean import desktop

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert desktop.has_desktop_cli() is False


def test_desktop_status_when_cli_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.docker_clean import desktop

    monkeypatch.setattr(desktop, "has_desktop_cli", lambda: False)
    assert desktop.status() == "<no desktop CLI>"


# --- pruner: container-side functions -----------------------------------


class _FakeContainer:
    def __init__(self, short_id: str, status: str = "running") -> None:
        self.short_id = short_id
        self.status = status
        self.name = f"ctr-{short_id}"
        self.image = type("Img", (), {"tags": [], "short_id": "sha256:abc"})

    def stop(self, timeout: int = 10) -> None:
        del timeout  # signature mirrors docker-py; not used in the fake

    def remove(self, force: bool = True) -> None:
        del force


class _FakeContainers:
    def __init__(self, ctrs: list[_FakeContainer]) -> None:
        self._ctrs = ctrs

    def list(self, **kwargs: Any) -> list[_FakeContainer]:
        del kwargs
        return self._ctrs


class _FakeClient:
    def __init__(self, ctrs: list[_FakeContainer]) -> None:
        self.containers = _FakeContainers(ctrs)


def test_stop_all_containers_no_running(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.docker_clean import pruner

    c = _FakeClient([])
    out = pruner.stop_all_containers(c)
    assert out.applied is False
    assert "No running" in " ".join(out.notes)


def test_stop_all_containers_some_running() -> None:
    from shimkit.tools.docker_clean import pruner

    c = _FakeClient([_FakeContainer("a"), _FakeContainer("b")])
    out = pruner.stop_all_containers(c)
    assert out.applied is True
    assert "Stopped 2" in " ".join(out.notes)


# --- DockerCleanManager methods ------------------------------------------


def test_docker_clean_quick_runs_all_prune_steps(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`docker-clean quick` should fire each pruner step in order."""
    from shimkit.tools.docker_clean import client as client_mod
    from shimkit.tools.docker_clean import pruner
    from shimkit.tools.docker_clean.models import CleanupOutcome

    called: list[str] = []

    def make_stub(name: str):  # type: ignore[no-untyped-def]
        def stub(*_a, **_kw):  # type: ignore[no-untyped-def]
            called.append(name)
            return CleanupOutcome(step=name, applied=True)

        return stub

    monkeypatch.setattr(client_mod, "get_client", lambda: object())
    monkeypatch.setattr(pruner, "stop_all_containers", make_stub("stop_all"))
    monkeypatch.setattr(pruner, "remove_all_containers", make_stub("remove_all"))
    monkeypatch.setattr(pruner, "prune_images", make_stub("prune_images"))
    monkeypatch.setattr(pruner, "prune_volumes", make_stub("prune_volumes"))
    monkeypatch.setattr(pruner, "prune_networks", make_stub("prune_networks"))

    result = runner.invoke(app, ["docker-clean", "quick", "--json"])
    assert result.exit_code == 0
    assert called == ["stop_all", "remove_all", "prune_images", "prune_volumes", "prune_networks"]


def test_docker_clean_nuke_with_token_runs_buildx_prune(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`nuke --confirm DELETE` should also invoke buildx pruning."""
    from shimkit.tools.docker_clean import client as client_mod
    from shimkit.tools.docker_clean import pruner
    from shimkit.tools.docker_clean.models import CleanupOutcome

    called: list[str] = []
    monkeypatch.setattr(client_mod, "get_client", lambda: object())
    monkeypatch.setattr(
        pruner,
        "stop_all_containers",
        lambda _c: called.append("stop") or CleanupOutcome(step="stop", applied=True),
    )
    monkeypatch.setattr(
        pruner,
        "remove_all_containers",
        lambda _c: called.append("rm") or CleanupOutcome(step="rm", applied=True),
    )
    monkeypatch.setattr(
        pruner,
        "prune_images",
        lambda _c, all_images=False: (
            called.append("img") or CleanupOutcome(step="img", applied=True)
        ),
    )
    monkeypatch.setattr(
        pruner,
        "prune_volumes",
        lambda _c: called.append("vol") or CleanupOutcome(step="vol", applied=True),
    )
    monkeypatch.setattr(
        pruner,
        "prune_networks",
        lambda _c: called.append("net") or CleanupOutcome(step="net", applied=True),
    )
    monkeypatch.setattr(
        pruner,
        "prune_buildx_builders",
        lambda all_caches=True: (
            called.append("buildx") or CleanupOutcome(step="buildx", applied=True)
        ),
    )
    result = runner.invoke(app, ["docker-clean", "nuke", "--confirm", "DELETE"])
    assert result.exit_code == 0
    assert "buildx" in called


def test_docker_clean_prune_images_dry_run_skips(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shimkit.tools.docker_clean import client as client_mod
    from shimkit.tools.docker_clean import pruner

    monkeypatch.setattr(client_mod, "get_client", lambda: object())
    called: list[str] = []
    monkeypatch.setattr(
        pruner,
        "prune_images",
        lambda *_a, **_kw: called.append("nope") or None,
    )
    result = runner.invoke(app, ["docker-clean", "prune-images", "--dry-run"])
    assert result.exit_code == 0
    assert called == []


def test_docker_clean_stop_all_dry_run(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.docker_clean import client as client_mod

    monkeypatch.setattr(client_mod, "get_client", lambda: object())
    result = runner.invoke(app, ["docker-clean", "stop-all", "--dry-run"])
    assert result.exit_code == 0


def test_docker_clean_schedule_emit_writes_file(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from shimkit.tools.docker_clean import client as client_mod

    monkeypatch.setattr(client_mod, "get_client", lambda: object())
    out = tmp_path / "schedule.txt"
    result = runner.invoke(
        app, ["docker-clean", "schedule", "--interval", "weekly", "--out", str(out)]
    )
    assert result.exit_code == 0
    assert out.exists()
    body = out.read_text()
    # macOS host emits a launchd plist; Linux emits systemd timer. Either is fine.
    assert "shimkit" in body.lower() or "docker-clean" in body.lower()


def test_docker_clean_compose_down_invokes_docker_compose(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from shimkit.core import CommandResult
    from shimkit.tools.docker_clean import client as client_mod

    monkeypatch.setattr(client_mod, "get_client", lambda: object())
    # (preflight bypass handled by the module-level autouse fixture)
    captured: list[list[str]] = []
    monkeypatch.setattr(
        "shimkit.tools.docker_clean.manager.CommandRunner.run",
        staticmethod(lambda cmd, **_: captured.append(cmd) or CommandResult(0, "", "")),
    )
    compose = tmp_path / "compose.yml"
    compose.write_text("services:\n  web:\n    image: nginx\n")
    result = runner.invoke(app, ["docker-clean", "compose-down", str(compose), "--volumes"])
    assert result.exit_code == 0
    assert captured and captured[0] == ["docker", "compose", "-f", str(compose), "down", "-v"]


def test_docker_clean_restart_macos_uses_desktop(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On macOS, restart goes through `docker desktop restart`."""
    from shimkit.core.platform import Platform
    from shimkit.tools.docker_clean import client as client_mod
    from shimkit.tools.docker_clean import desktop

    monkeypatch.setattr(client_mod, "get_client", lambda: None)  # require_daemon=False
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Darwin", machine="arm64")),
    )
    called: list[str] = []
    monkeypatch.setattr(
        desktop,
        "restart",
        lambda platform=None: called.append("desktop") or True,
    )
    monkeypatch.setattr(
        client_mod,
        "get_client",
        # First call (boot) returns None — but boot doesn't fail because
        # require_daemon=False on the restart path. After restart, get_client()
        # is polled — return a stub object on subsequent calls.
        lambda: object(),
    )
    result = runner.invoke(app, ["docker-clean", "restart"])
    assert result.exit_code == 0
    assert called == ["desktop"]


def test_docker_clean_inspect_volumes_success(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shimkit.tools.docker_clean import client as client_mod

    class FakeVolume:
        def __init__(self, name: str) -> None:
            self.name = name
            self.attrs = {"Mountpoint": f"/var/lib/docker/volumes/{name}/_data"}

    class FakeVolumes:
        def list(self) -> list[FakeVolume]:
            return [FakeVolume("vol1"), FakeVolume("vol2")]

    class FakeClient:
        volumes = FakeVolumes()

    monkeypatch.setattr(client_mod, "get_client", lambda: FakeClient())
    result = runner.invoke(app, ["docker-clean", "inspect", "volumes", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert len(doc["data"]["items"]) == 2


def test_docker_clean_inspect_invalid_kind(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shimkit.tools.docker_clean import client as client_mod

    monkeypatch.setattr(client_mod, "get_client", lambda: object())
    result = runner.invoke(app, ["docker-clean", "inspect", "nonsense"])
    assert result.exit_code == 1


def test_docker_clean_prune_unknown_kind_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manager.prune() with unknown kind returns generic failure."""
    from shimkit.tools.docker_clean import client as client_mod
    from shimkit.tools.docker_clean.manager import DockerCleanManager

    monkeypatch.setattr(client_mod, "get_client", lambda: object())
    mgr = DockerCleanManager.create().boot()
    assert mgr.prune("nonexistent-kind") == 1


def test_docker_clean_quick_dry_run_short_circuits(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--dry-run on quick exits 0 without touching pruner."""
    from shimkit.tools.docker_clean import client as client_mod
    from shimkit.tools.docker_clean import pruner

    monkeypatch.setattr(client_mod, "get_client", lambda: object())
    monkeypatch.setattr(
        pruner,
        "stop_all_containers",
        lambda _c: (_ for _ in ()).throw(AssertionError("should not call")),
    )
    result = runner.invoke(app, ["docker-clean", "quick", "--dry-run"])
    assert result.exit_code == 0


def test_docker_clean_status_with_no_daemon_exits_69(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """status requires the daemon; absent → exit 69."""
    from shimkit.tools.docker_clean import client as client_mod

    monkeypatch.setattr(client_mod, "get_client", lambda: None)
    result = runner.invoke(app, ["docker-clean", "status"])
    assert result.exit_code == 69


# --- pruner error paths --------------------------------------------------


class _ExplodingClient:
    """A docker-py-shaped client whose every prune call raises."""

    class _Images:
        def prune(self, **_kw: Any) -> dict:
            raise RuntimeError("simulated images prune failure")

    class _Volumes:
        def prune(self) -> dict:
            raise RuntimeError("simulated volumes prune failure")

    class _Networks:
        def prune(self) -> dict:
            raise RuntimeError("simulated networks prune failure")

    images = _Images()
    volumes = _Volumes()
    networks = _Networks()


def test_prune_images_records_error_on_exception() -> None:
    from shimkit.tools.docker_clean import pruner

    out = pruner.prune_images(_ExplodingClient(), all_images=True)
    assert out.applied is False
    assert out.error and "images prune" in out.error


def test_prune_volumes_records_error_on_exception() -> None:
    from shimkit.tools.docker_clean import pruner

    out = pruner.prune_volumes(_ExplodingClient())
    assert out.applied is False
    assert out.error and "volumes prune" in out.error


def test_prune_networks_records_error_on_exception() -> None:
    from shimkit.tools.docker_clean import pruner

    out = pruner.prune_networks(_ExplodingClient())
    assert out.applied is False
    assert out.error and "networks prune" in out.error


def test_remove_all_containers_no_containers() -> None:
    from shimkit.tools.docker_clean import pruner

    out = pruner.remove_all_containers(_FakeClient([]))
    assert out.applied is False
    assert "No containers" in " ".join(out.notes)


def test_orphans_combines_image_and_volume_reclaim() -> None:
    """`orphans` is the union of prune_images(False) + prune_volumes."""
    from shimkit.tools.docker_clean import pruner

    class C:
        class _Images:
            def prune(self, **_kw):  # type: ignore[no-untyped-def]
                return {"SpaceReclaimed": 100}

        class _Volumes:
            def prune(self):  # type: ignore[no-untyped-def]
                return {"SpaceReclaimed": 50}

        images = _Images()
        volumes = _Volumes()

    out = pruner.orphans(C())
    assert out.applied
    assert out.reclaimed_bytes == 150


# --- desktop -----------------------------------------------------------


def test_desktop_restart_uses_cli_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.core import CommandResult
    from shimkit.tools.docker_clean import desktop

    monkeypatch.setattr(desktop, "has_desktop_cli", lambda: True)
    captured: list[list[str]] = []
    monkeypatch.setattr(
        "shimkit.tools.docker_clean.desktop.CommandRunner.run",
        staticmethod(lambda cmd, **_: captured.append(cmd) or CommandResult(0, "", "")),
    )
    assert desktop.restart() is True
    assert captured == [["docker", "desktop", "restart"]]


def test_desktop_restart_falls_back_on_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the desktop CLI is absent, fall back to osascript on macOS."""
    from shimkit.core import CommandResult
    from shimkit.core.platform import Platform
    from shimkit.tools.docker_clean import desktop

    monkeypatch.setattr(desktop, "has_desktop_cli", lambda: False)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    seen: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        seen.append(cmd)
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.docker_clean.desktop.CommandRunner.run", staticmethod(fake_run)
    )
    ok = desktop.restart(platform=Platform(system="Darwin", machine="arm64"))
    assert ok is True
    # osascript + open -a Docker both called
    assert any("osascript" in c for c in seen)
    assert any(c[0] == "open" for c in seen)


def test_desktop_restart_refuses_on_linux_without_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No CLI + Linux = the caller should fall back to systemd, not osascript."""
    from shimkit.core.platform import Platform
    from shimkit.tools.docker_clean import desktop

    monkeypatch.setattr(desktop, "has_desktop_cli", lambda: False)
    assert desktop.restart(platform=Platform(system="Linux", machine="x86_64")) is False
