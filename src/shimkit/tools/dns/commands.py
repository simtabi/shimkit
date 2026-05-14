"""Typer subcommands for ``shimkit dns``."""

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

dns_app = typer.Typer(
    name="dns",
    help="macOS DNS resolver recovery and diagnostics.",
    no_args_is_help=False,
)


def _bootstrap(log_file: str | None, verbose: bool, quiet: bool = False) -> None:
    """Wire logging + UI based on shared flags. Idempotent across subcommands."""
    if verbose:
        set_verbose(True)
    if quiet:
        UI.set_quiet(True)
    if log_file:
        attach_file_handler(log_file)


@dns_app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    quiet: bool = QUIET,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
    no_color: bool = NO_COLOR,
    color: str = COLOR,
    no_input: bool = NO_INPUT,
) -> None:
    """Apply universal flags before dispatching to a subcommand.

    Place these before the subcommand: ``shimkit dns --no-color flush``.
    Per-subcommand flags (``--json``, ``--dry-run``, ``--yes``,
    ``--force``) go after the subcommand.
    """
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
        from .manager import DnsManager

        DnsManager.create().boot().run()


@dns_app.command("diagnose")
def diagnose(
    json_out: bool = JSON_OUT,
    log_file: str = LOG_FILE,
    verbose: bool = VERBOSE,
    quiet: bool = QUIET,
) -> None:
    """Report resolver chain, active service, and known interference sources."""
    _bootstrap(log_file, verbose, quiet)
    from .manager import DnsManager

    code = DnsManager.create().boot().diagnose(json_out=json_out)
    raise typer.Exit(code)


@dns_app.command("flush")
def flush(
    json_out: bool = JSON_OUT,
    log_file: str = LOG_FILE,
    verbose: bool = VERBOSE,
) -> None:
    """Flush DNS cache and HUP mDNSResponder. The 80% case."""
    _bootstrap(log_file, verbose)
    from .manager import DnsManager

    code = DnsManager.create().boot().flush(json_out=json_out)
    raise typer.Exit(code)


@dns_app.command("show")
def show(
    service: str = typer.Option(
        None, "--service", help="Override the auto-detected network service."
    ),
    json_out: bool = JSON_OUT,
) -> None:
    """Print the configured DNS servers for the active network service."""
    from .manager import DnsManager

    code = DnsManager.create().boot().show(service=service, json_out=json_out)
    raise typer.Exit(code)


@dns_app.command("set")
def set_servers(
    servers: list[str] = typer.Argument(..., help="One or more IP addresses."),
    service: str = typer.Option(None, "--service"),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Set DNS servers for the active service. Empty list resets to DHCP."""
    from .manager import DnsManager

    if not dry_run and not Menu.prompt_for_change(
        f"Set DNS for {service or '<active service>'} to {', '.join(servers)}",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)

    code = DnsManager.create().boot().set_servers(servers, service=service, dry_run=dry_run)
    raise typer.Exit(code)


@dns_app.command("reset")
def reset(
    confirm: str = typer.Option(
        None,
        "--confirm",
        help="Pass the literal token from config.tools.dns.reset_confirm_token.",
    ),
    service: str = typer.Option(None, "--service"),
) -> None:
    """Reset DNS to DHCP for the active service (severe — token required)."""
    from .manager import DnsManager

    code = DnsManager.create().boot().reset(confirm=confirm, service=service)
    raise typer.Exit(code)


@dns_app.command("test")
def test(
    domains: list[str] = typer.Argument(None, help="Domains to test (defaults from config)."),
    json_out: bool = JSON_OUT,
) -> None:
    """Resolve test domains via the system resolver and report each."""
    from .manager import DnsManager

    code = DnsManager.create().boot().test(domains or [], json_out=json_out)
    raise typer.Exit(code)


profile_app = typer.Typer(name="profile", help="Inspect installed DNS configuration profiles.")
dns_app.add_typer(profile_app)


@profile_app.command("list")
def profile_list(json_out: bool = JSON_OUT) -> None:
    """List installed configuration profiles (encrypted-DNS providers, MDM, etc.)."""
    from .manager import DnsManager

    code = DnsManager.create().boot().profile_list(json_out=json_out)
    raise typer.Exit(code)


@dns_app.command("fix")
def fix(
    start_at: int = typer.Option(1, "--start-at", min=1, max=6),
    stop_at: int = typer.Option(6, "--stop-at", min=1, max=6),
    skip_nuclear: bool = typer.Option(False, "--skip-nuclear"),
    profile: str = typer.Option("cloudflare", "--profile"),
    confirm: str = typer.Option(
        None,
        "--confirm",
        help="Required for the nuclear step (token from config).",
    ),
    json_out: bool = JSON_OUT,
    log_file: str = LOG_FILE,
    verbose: bool = VERBOSE,
) -> None:
    """Run the 6-step DNS recovery escalation. Stops at the first step that fixes resolution."""
    _bootstrap(log_file, verbose)
    from .manager import DnsManager

    code = (
        DnsManager.create()
        .boot()
        .fix(
            start_at=start_at,
            stop_at=stop_at,
            skip_nuclear=skip_nuclear,
            profile=profile,
            nuclear_confirm=confirm,
            json_out=json_out,
        )
    )
    raise typer.Exit(code)


@dns_app.command("rollback")
def rollback() -> None:
    """Restore the most recent SystemConfiguration plist backup made by `fix --nuclear`."""
    from .manager import DnsManager

    code = DnsManager.create().boot().rollback()
    raise typer.Exit(code)


diagnostics_app = typer.Typer(name="diagnostics", help="Diagnostic bundles for support tickets.")
dns_app.add_typer(diagnostics_app)


@diagnostics_app.command("export")
def diagnostics_export(
    out: Path = typer.Option(
        None,
        "--out",
        help="Output path. Defaults to backup_dir/diagnostics-<timestamp>.txt.",
    ),
) -> None:
    """Dump a diagnostic bundle (scutil --dns, ifconfig, service config)."""
    from .manager import DnsManager

    code = DnsManager.create().boot().diagnostics_export(out)
    raise typer.Exit(code)
