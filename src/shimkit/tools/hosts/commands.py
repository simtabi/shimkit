"""Typer subcommands for ``shimkit hosts``."""

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

hosts_app = typer.Typer(
    name="hosts",
    help="View / mutate /etc/hosts with atomic-write + timestamped backup.",
    no_args_is_help=False,
)


def _hosts_override(p: str | None) -> Path | None:
    return Path(p).expanduser() if p else None


@hosts_app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    quiet: bool = QUIET,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
    no_color: bool = NO_COLOR,
    color: str = COLOR,
    no_input: bool = NO_INPUT,
) -> None:
    """Universal flags. Bare ``shimkit hosts`` opens the interactive menu."""
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
        from .manager import HostsManager

        HostsManager.create().boot().run()


@hosts_app.command("show")
def show(
    hosts_path: str = typer.Option(None, "--path", help="Override the hosts file (testing)."),
    json_out: bool = JSON_OUT,
) -> None:
    """Print every entry in the hosts file."""
    from .manager import HostsManager

    code = (
        HostsManager.create()
        .boot(hosts_path_override=_hosts_override(hosts_path))
        .show(json_out=json_out)
    )
    raise typer.Exit(code)


@hosts_app.command("add")
def add(
    ip: str = typer.Argument(..., help="IPv4 or IPv6 address."),
    name: str = typer.Argument(..., help="Hostname to map."),
    hosts_path: str = typer.Option(None, "--path"),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Append ``<ip> <name>`` (idempotent). MODERATE prompt."""
    from .manager import HostsManager

    if not dry_run and not Menu.prompt_for_change(
        f"Add {ip} {name} to hosts",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        HostsManager.create()
        .boot(hosts_path_override=_hosts_override(hosts_path))
        .add(ip, name, dry_run=dry_run)
    )
    raise typer.Exit(code)


@hosts_app.command("remove")
def remove(
    name: str = typer.Argument(..., help="Hostname to remove (all entries)."),
    hosts_path: str = typer.Option(None, "--path"),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Remove every entry whose name matches ``NAME``. MODERATE prompt."""
    from .manager import HostsManager

    if not dry_run and not Menu.prompt_for_change(
        f"Remove every entry for {name}",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        HostsManager.create()
        .boot(hosts_path_override=_hosts_override(hosts_path))
        .remove(name, dry_run=dry_run)
    )
    raise typer.Exit(code)


@hosts_app.command("block")
def block(
    domain: str = typer.Argument(..., help="Domain to redirect to 127.0.0.1."),
    hosts_path: str = typer.Option(None, "--path"),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Add ``127.0.0.1 DOMAIN`` (alias for ``add 127.0.0.1 DOMAIN``)."""
    from .manager import HostsManager

    if not dry_run and not Menu.prompt_for_change(
        f"Block {domain} (add 127.0.0.1 entry)",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        HostsManager.create()
        .boot(hosts_path_override=_hosts_override(hosts_path))
        .block(domain, dry_run=dry_run)
    )
    raise typer.Exit(code)


@hosts_app.command("unblock")
def unblock(
    domain: str = typer.Argument(...),
    hosts_path: str = typer.Option(None, "--path"),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Remove ``DOMAIN`` entries (alias for ``remove DOMAIN``)."""
    from .manager import HostsManager

    if not dry_run and not Menu.prompt_for_change(
        f"Unblock {domain}",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        HostsManager.create()
        .boot(hosts_path_override=_hosts_override(hosts_path))
        .unblock(domain, dry_run=dry_run)
    )
    raise typer.Exit(code)


@hosts_app.command("apply-list")
def apply_list(
    source: str = typer.Argument(
        ...,
        help="URL (http/https) or local path to a StevenBlack-style list.",
    ),
    hosts_path: str = typer.Option(None, "--path"),
    confirm: str = typer.Option(
        "",
        "--confirm",
        help="Severe-tier token. See `tools.hosts.apply_list_severe_token`.",
    ),
    dry_run: bool = DRY_RUN,
) -> None:
    """Apply a bulk block list. SEVERE — token required."""
    from shimkit.config import get_config

    from .manager import HostsManager

    cfg = get_config().tools.hosts
    if not dry_run and confirm != cfg.apply_list_severe_token:
        UI.error(
            "apply-list is severe-tier (it can write thousands of "
            "entries). Pass `--confirm "
            f"{cfg.apply_list_severe_token}` to proceed."
        )
        raise typer.Exit(1)
    code = (
        HostsManager.create()
        .boot(hosts_path_override=_hosts_override(hosts_path))
        .apply_list(source, dry_run=dry_run)
    )
    raise typer.Exit(code)


@hosts_app.command("rollback")
def rollback(
    hosts_path: str = typer.Option(None, "--path"),
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Restore the most recent backup. MODERATE prompt."""
    from .manager import HostsManager

    if not Menu.prompt_for_change(
        "Restore the most recent hosts backup",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt.")
        raise typer.Exit(1)
    code = HostsManager.create().boot(hosts_path_override=_hosts_override(hosts_path)).rollback()
    raise typer.Exit(code)
