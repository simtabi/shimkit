"""Typer subcommands for ``shimkit docker-clean``."""

from __future__ import annotations

from pathlib import Path

import typer

from shimkit.core import UI, Menu, attach_file_handler, set_verbose
from shimkit.core.cli_flags import (
    COLOR,
    DRY_RUN,
    FORCE,
    JSON_OUT,
    LOG_FILE,
    NO_COLOR,
    NO_INPUT,
    QUIET,
    VERBOSE,
    YES,
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
def _root(
    ctx: typer.Context,
    quiet: bool = QUIET,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
    no_color: bool = NO_COLOR,
    color: str = COLOR,
    no_input: bool = NO_INPUT,
) -> None:
    """Apply universal flags before dispatching to a subcommand."""
    if verbose:
        set_verbose(True)
    if quiet:
        UI.set_quiet(True)
    if no_color:
        UI.set_color_mode("never")
    elif color:
        UI.set_color_mode(color)
    if no_input:
        UI.set_no_input(True)
    if log_file:
        attach_file_handler(log_file)
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


def _prune_with_prompt(kind: str, label: str, dry_run: bool, yes: bool, force: bool) -> None:
    """MODERATE-tier prompt + dispatch shared by every `prune-*` command."""
    from .manager import DockerCleanManager

    if not dry_run and not Menu.prompt_for_change(
        f"Remove {label}",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)

    code = DockerCleanManager.create().boot().prune(kind, dry_run=dry_run)
    raise typer.Exit(code)


@docker_clean_app.command("prune-images")
def prune_images(
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """`docker image prune -a` (removes images not used by any container)."""
    _prune_with_prompt("images", "all unused images", dry_run, yes, force)


@docker_clean_app.command("prune-volumes")
def prune_volumes(
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """`docker volume prune` (with confirmation)."""
    _prune_with_prompt("volumes", "all unused volumes (DATA LOSS RISK)", dry_run, yes, force)


@docker_clean_app.command("prune-networks")
def prune_networks(
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """`docker network prune` (custom networks only)."""
    _prune_with_prompt("networks", "all unused custom networks", dry_run, yes, force)


@docker_clean_app.command("prune-builders")
def prune_builders(
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Iterate `docker buildx ls` and prune each builder's cache."""
    _prune_with_prompt(
        "builders",
        "all buildx caches (will re-download on next build)",
        dry_run,
        yes,
        force,
    )


@docker_clean_app.command("orphans")
def orphans(
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Remove dangling images + unused volumes only (narrower than system prune)."""
    _prune_with_prompt(
        "orphans",
        "dangling images + unused volumes",
        dry_run,
        yes,
        force,
    )


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

    code = DockerCleanManager.create().boot(require_daemon=False).schedule_emit(interval, out)
    raise typer.Exit(code)
