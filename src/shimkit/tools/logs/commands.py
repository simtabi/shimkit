"""Typer subcommands for ``shimkit logs``."""

from __future__ import annotations

import typer

from shimkit.core import UI, attach_file_handler, set_verbose
from shimkit.core.cli_flags import (
    COLOR,
    JSON_OUT,
    LOG_FILE,
    NO_COLOR,
    NO_INPUT,
    QUIET,
    VERBOSE,
)

logs_app = typer.Typer(
    name="logs",
    help="Tail / grep system logs (macOS `log`, Linux journalctl).",
    no_args_is_help=False,
)


@logs_app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    quiet: bool = QUIET,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
    no_color: bool = NO_COLOR,
    color: str = COLOR,
    no_input: bool = NO_INPUT,
) -> None:
    """Universal flags. Bare ``shimkit logs`` opens the interactive menu."""
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
        from .manager import LogsManager

        LogsManager.create().boot().run()


@logs_app.command("tail")
def tail(
    lines: int = typer.Option(
        None, "--lines", "-n", min=1, max=100_000, help="Lines to show."
    ),
    follow: bool = typer.Option(
        False, "--follow", "-f", help="Stream new entries as they arrive."
    ),
    predicate: str = typer.Option(
        None,
        "--predicate",
        "-p",
        help=(
            "macOS: NSPredicate string passed to `log show --predicate`. "
            "Linux: `journalctl --grep PATTERN`."
        ),
    ),
    unit: str = typer.Option(
        None,
        "--unit",
        "-u",
        help="Linux only: filter to one systemd unit (e.g. `sshd`).",
    ),
    json_out: bool = JSON_OUT,
) -> None:
    """Show the last N log lines."""
    from .manager import LogsManager

    code = (
        LogsManager.create()
        .boot()
        .tail(
            lines=lines,
            follow=follow,
            predicate=predicate,
            unit=unit,
            json_out=json_out,
        )
    )
    raise typer.Exit(code)


@logs_app.command("grep")
def grep_cmd(
    pattern: str = typer.Argument(..., help="Text to search for in log bodies."),
    since: str = typer.Option(
        None,
        "--since",
        help="macOS: `--last` arg (e.g. `1h`, `30m`). Linux: journalctl `--since` (e.g. `1 hour ago`).",
    ),
    unit: str = typer.Option(
        None, "--unit", "-u", help="Linux only: filter to one systemd unit."
    ),
    json_out: bool = JSON_OUT,
) -> None:
    """Search log history for PATTERN."""
    from .manager import LogsManager

    code = (
        LogsManager.create()
        .boot()
        .grep(pattern, since=since, unit=unit, json_out=json_out)
    )
    raise typer.Exit(code)


system_app = typer.Typer(name="system", help="System log views.")
logs_app.add_typer(system_app)


@system_app.command("show")
def system_show(
    priority: str = typer.Option(
        None,
        "--priority",
        "-P",
        help=(
            "macOS: error|fault|info|debug (maps to NSPredicate `messageType`). "
            "Linux: journalctl priority arg (emerg|alert|crit|err|warning|notice|info|debug)."
        ),
    ),
    lines: int = typer.Option(
        None, "--lines", "-n", min=1, max=100_000
    ),
    json_out: bool = JSON_OUT,
) -> None:
    """Show recent system log lines filtered by priority."""
    from .manager import LogsManager

    code = (
        LogsManager.create()
        .boot()
        .system_show(priority=priority, lines=lines, json_out=json_out)
    )
    raise typer.Exit(code)
