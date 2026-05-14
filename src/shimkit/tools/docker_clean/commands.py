"""Typer subcommands for ``shimkit docker-clean``."""

from __future__ import annotations

from pathlib import Path

import typer

from shimkit.core import UI, attach_file_handler, set_verbose
from shimkit.core.cli_flags import (
    DRY_RUN,
    JSON_OUT,
    LOG_FILE,
    QUIET,
    VERBOSE,
)

docker_clean_app = typer.Typer(
    name="docker-clean",
    help="Docker resource cleanup (Linux + macOS + WSL).",
    no_args_is_help=False,
)


def _bootstrap(log_file: str | None, verbose: bool, quiet: bool = False) -> None:
    if verbose:
        set_verbose(True)
    if quiet:
        UI.set_quiet(True)
    if log_file:
        attach_file_handler(log_file)


@docker_clean_app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        from .manager import DockerCleanManager

        DockerCleanManager.create().boot().run()


@docker_clean_app.command("status")
def status(
    json_out: bool = JSON_OUT,
    log_file: str = LOG_FILE,
    verbose: bool = VERBOSE,
    quiet: bool = QUIET,
) -> None:
    """Print disk usage and desktop status."""
    _bootstrap(log_file, verbose, quiet)
    from .manager import DockerCleanManager

    code = DockerCleanManager.create().boot().status(json_out=json_out)
    raise typer.Exit(code)


@docker_clean_app.command("quick")
def quick(
    dry_run: bool = DRY_RUN,
    json_out: bool = JSON_OUT,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
) -> None:
    """Stop containers, remove them, prune images/volumes/networks."""
    _bootstrap(log_file, verbose, False)
    from .manager import DockerCleanManager

    code = DockerCleanManager.create().boot().quick(dry_run=dry_run, json_out=json_out)
    raise typer.Exit(code)


@docker_clean_app.command("nuke")
def nuke(
    confirm: str = typer.Option(
        None,
        "--confirm",
        help="Pass the literal token from config.tools.docker_clean.nuke_confirm_token.",
    ),
    json_out: bool = JSON_OUT,
) -> None:
    """Remove EVERYTHING (severe — token required)."""
    from .manager import DockerCleanManager

    code = DockerCleanManager.create().boot().nuke(confirm=confirm, json_out=json_out)
    raise typer.Exit(code)


@docker_clean_app.command("restart")
def restart() -> None:
    """Restart the Docker daemon (Desktop on macOS, systemd on Linux)."""
    from .manager import DockerCleanManager

    code = DockerCleanManager.create().boot(require_daemon=False).restart()
    raise typer.Exit(code)


@docker_clean_app.command("stop-all")
def stop_all(dry_run: bool = DRY_RUN) -> None:
    """Stop all currently running containers."""
    from .manager import DockerCleanManager

    code = DockerCleanManager.create().boot().stop_all(dry_run=dry_run)
    raise typer.Exit(code)


@docker_clean_app.command("prune-images")
def prune_images(dry_run: bool = DRY_RUN) -> None:
    """`docker image prune -a` (removes images not used by any container)."""
    from .manager import DockerCleanManager

    code = DockerCleanManager.create().boot().prune("images", dry_run=dry_run)
    raise typer.Exit(code)


@docker_clean_app.command("prune-volumes")
def prune_volumes(dry_run: bool = DRY_RUN) -> None:
    """`docker volume prune` (with confirmation)."""
    from .manager import DockerCleanManager

    code = DockerCleanManager.create().boot().prune("volumes", dry_run=dry_run)
    raise typer.Exit(code)


@docker_clean_app.command("prune-networks")
def prune_networks(dry_run: bool = DRY_RUN) -> None:
    """`docker network prune` (custom networks only)."""
    from .manager import DockerCleanManager

    code = DockerCleanManager.create().boot().prune("networks", dry_run=dry_run)
    raise typer.Exit(code)


@docker_clean_app.command("prune-builders")
def prune_builders(dry_run: bool = DRY_RUN) -> None:
    """Iterate `docker buildx ls` and prune each builder's cache."""
    from .manager import DockerCleanManager

    code = DockerCleanManager.create().boot().prune("builders", dry_run=dry_run)
    raise typer.Exit(code)


@docker_clean_app.command("orphans")
def orphans(dry_run: bool = DRY_RUN) -> None:
    """Remove dangling images + unused volumes only (narrower than system prune)."""
    from .manager import DockerCleanManager

    code = DockerCleanManager.create().boot().prune("orphans", dry_run=dry_run)
    raise typer.Exit(code)


@docker_clean_app.command("inspect")
def inspect(
    kind: str = typer.Argument(..., help="containers | images | volumes | networks | cache"),
    json_out: bool = JSON_OUT,
) -> None:
    """Detailed listing for one resource kind."""
    from .manager import DockerCleanManager

    code = DockerCleanManager.create().boot().inspect(kind, json_out=json_out)
    raise typer.Exit(code)


@docker_clean_app.command("compose-down")
def compose_down(
    path: Path = typer.Argument(..., help="Path to docker-compose.yml"),
    with_volumes: bool = typer.Option(False, "--volumes", "-v"),
) -> None:
    """Run `docker compose down [-v]` for one project."""
    from .manager import DockerCleanManager

    code = DockerCleanManager.create().boot().compose_down(path, with_volumes=with_volumes)
    raise typer.Exit(code)


@docker_clean_app.command("schedule")
def schedule_cmd(
    interval: str = typer.Option("weekly", "--interval", help="daily | weekly"),
    out: Path = typer.Option(None, "--out", help="Write snippet to PATH instead of stdout."),
) -> None:
    """Emit (do not install) a launchd plist, systemd timer, or cron line."""
    from .manager import DockerCleanManager

    code = (
        DockerCleanManager.create()
        .boot(require_daemon=False)
        .schedule_emit(interval, out)
    )
    raise typer.Exit(code)
