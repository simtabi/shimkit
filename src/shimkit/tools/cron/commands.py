"""Typer subcommands for ``shimkit cron``."""

from __future__ import annotations

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

cron_app = typer.Typer(
    name="cron",
    help="Manage shimkit-tagged entries in your user crontab (macOS + Linux).",
    no_args_is_help=False,
)


@cron_app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    quiet: bool = QUIET,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
    no_color: bool = NO_COLOR,
    color: str = COLOR,
    no_input: bool = NO_INPUT,
) -> None:
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
        UI.header("shimkit cron")
        UI.line("Commands: list / add / remove / show / rollback")


@cron_app.command("show")
def show(json_out: bool = JSON_OUT) -> None:
    """Print the entire user crontab (shimkit-managed + user-authored)."""
    from .manager import CronManager

    code = CronManager.create().boot().show(json_out=json_out)
    raise typer.Exit(code)


@cron_app.command("list")
def list_entries(json_out: bool = JSON_OUT) -> None:
    """List shimkit-managed entries only."""
    from .manager import CronManager

    code = CronManager.create().boot().list_entries(json_out=json_out)
    raise typer.Exit(code)


@cron_app.command("add")
def add(
    name: str = typer.Option(..., "--name", help="Slug (a-z, 0-9, _, -; starts with letter)."),
    schedule: str = typer.Option(
        ...,
        "--schedule",
        help="5-field cron expression or @reboot/@daily/etc.",
    ),
    command: str = typer.Option(..., "--cmd", help="Command to run."),
    comment: str = typer.Option(None, "--comment", help="Free-text comment."),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Add a shimkit-managed cron entry. MODERATE prompt."""
    from .manager import CronManager

    if not dry_run and not Menu.prompt_for_change(
        f"Install cron entry {name!r} ({schedule}: {command})",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        CronManager.create()
        .boot()
        .add(
            name=name,
            schedule=schedule,
            command=command,
            comment=comment,
            dry_run=dry_run,
        )
    )
    raise typer.Exit(code)


@cron_app.command("remove")
def remove(
    name: str = typer.Argument(..., help="Name of the shimkit-managed entry to remove."),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Remove a shimkit-managed cron entry. MODERATE prompt."""
    from .manager import CronManager

    if not dry_run and not Menu.prompt_for_change(
        f"Remove cron entry {name!r}",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = CronManager.create().boot().remove(name, dry_run=dry_run)
    raise typer.Exit(code)


@cron_app.command("rollback")
def rollback(
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Restore the most recent backup of the user crontab. MODERATE prompt."""
    from .manager import CronManager

    if not Menu.prompt_for_change(
        "Restore the latest crontab backup",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt.")
        raise typer.Exit(1)
    code = CronManager.create().boot().rollback()
    raise typer.Exit(code)
