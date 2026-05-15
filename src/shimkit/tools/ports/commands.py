"""Typer subcommands for ``shimkit ports``."""

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

ports_app = typer.Typer(
    name="ports",
    help="Inspect or kill the process holding a TCP/UDP port (macOS + Linux).",
    no_args_is_help=False,
)


@ports_app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    quiet: bool = QUIET,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
    no_color: bool = NO_COLOR,
    color: str = COLOR,
    no_input: bool = NO_INPUT,
) -> None:
    """Universal flags. Bare ``shimkit ports`` opens an interactive menu."""
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
        from .manager import PortsManager

        PortsManager.create().boot().run()


@ports_app.command("show")
def show(
    port: int = typer.Argument(None, min=1, max=65535, help="Optional port to narrow output to."),
    json_out: bool = JSON_OUT,
) -> None:
    """List listening TCP/UDP sockets and the processes holding them."""
    from .manager import PortsManager

    code = PortsManager.create().boot().show(port=port, json_out=json_out)
    raise typer.Exit(code)


@ports_app.command("kill")
def kill(
    port: int = typer.Argument(..., min=1, max=65535),
    signal: str = typer.Option(
        "TERM",
        "--signal",
        "-s",
        help="Signal to send. Allowed: TERM, KILL, INT, HUP.",
    ),
    confirm: str = typer.Option(
        "",
        "--confirm",
        help=(
            "Severe-tier token. Required when targeting pid 1 or a "
            "system-tier process (pid below the configured threshold)."
        ),
    ),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Signal every process holding ``PORT``.

    MODERATE prompt by default. SEVERE token required for system-tier
    targets (pid below ``tools.ports.system_pid_threshold``).
    """
    from shimkit.config import get_config

    from . import owners as _owners_mod
    from .manager import PortsManager

    mgr = PortsManager.create().boot()
    cfg = get_config().tools.ports

    # Surface targets before prompting so the user sees what they're
    # about to kill.
    targets = _owners_mod.filter_port(mgr.list_owners(), port)
    if not targets:
        UI.info(f"Nothing is holding port {port}.")
        raise typer.Exit(0)

    has_system_tier = any(o.pid <= cfg.system_pid_threshold for o in targets)

    if has_system_tier and confirm != cfg.init_pid_severe_token:
        UI.error(
            f"Refusing to kill a system-tier process on port {port}. "
            f"Pass --confirm {cfg.init_pid_severe_token} to override "
            "(severe tier — read the docs first)."
        )
        raise typer.Exit(1)

    if not dry_run and not Menu.prompt_for_change(
        f"Send SIG{signal.upper()} to {len(targets)} process(es) on port {port}",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)

    code = mgr.kill(port, signal=signal, dry_run=dry_run)
    raise typer.Exit(code)
