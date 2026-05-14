"""Typer subcommands for ``shimkit adguard``."""

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
    TIMEOUT,
    VERBOSE,
    YES,
)

adguard_app = typer.Typer(
    name="adguard",
    help="AdGuard Home port-conflict fixer (Linux).",
    no_args_is_help=False,
)


def _bootstrap(log_file: str | None, verbose: bool, quiet: bool = False) -> None:
    if verbose:
        set_verbose(True)
    if quiet:
        UI.set_quiet(True)
    if log_file:
        attach_file_handler(log_file)


@adguard_app.callback(invoke_without_command=True)
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
        from .manager import AdGuardManager

        AdGuardManager.create().boot().run()


@adguard_app.command("scan")
def scan(
    install: Path = typer.Option(None, "--install"),
    json_out: bool = JSON_OUT,
    quiet: bool = QUIET,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
) -> None:
    """Report port-owners and conflicts. Read-only."""
    _bootstrap(log_file, verbose, quiet)
    from .manager import AdGuardManager

    code = AdGuardManager.create().boot(install_override=install).scan(json_out=json_out)
    raise typer.Exit(code)


@adguard_app.command("fix")
def fix(
    install: Path = typer.Option(None, "--install"),
    dry_run: bool = DRY_RUN,
    remap_only: bool = typer.Option(False, "--remap-only"),
    dns_cleanup_only: bool = typer.Option(False, "--dns-cleanup-only"),
    migrate_from_pihole: bool = typer.Option(False, "--migrate-from-pihole"),
    json_out: bool = JSON_OUT,
    quiet: bool = QUIET,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
) -> None:
    """Remediate AGH port conflicts. See `docs/tools/adguard.md` for the decision tree."""
    _bootstrap(log_file, verbose, quiet)
    from .manager import AdGuardManager

    # `fix` writes to /etc/* and controls systemd units (unless --dry-run).
    code = (
        AdGuardManager.create()
        .boot(install_override=install, require_root=not dry_run)
        .fix(
            dry_run=dry_run,
            remap_only=remap_only,
            dns_cleanup_only=dns_cleanup_only,
            migrate_from_pihole=migrate_from_pihole,
            json_out=json_out,
        )
    )
    raise typer.Exit(code)


@adguard_app.command("verify")
def verify(
    install: Path = typer.Option(None, "--install"),
    timeout: float = TIMEOUT,
    json_out: bool = JSON_OUT,
) -> None:
    """Loopback DNS query + /control/status probe."""
    from .manager import AdGuardManager

    code = (
        AdGuardManager.create()
        .boot(install_override=install)
        .verify(json_out=json_out, timeout=timeout)
    )
    raise typer.Exit(code)


ports_app = typer.Typer(name="ports", help="Inspect or set AGH's DNS/HTTP ports.")
adguard_app.add_typer(ports_app)


@ports_app.command("show")
def ports_show(
    install: Path = typer.Option(None, "--install"),
    json_out: bool = JSON_OUT,
) -> None:
    """Print the configured dns.port / http.port from AdGuardHome.yaml."""
    from .manager import AdGuardManager

    code = AdGuardManager.create().boot(install_override=install).ports_show(json_out=json_out)
    raise typer.Exit(code)


@ports_app.command("set")
def ports_set(
    dns: int = typer.Option(..., "--dns", min=1, max=65535),
    http: int = typer.Option(..., "--http", min=1, max=65535),
    install: Path = typer.Option(None, "--install"),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Set AGH's DNS/HTTP ports (API-first, yaml fallback with service stop)."""
    from .manager import AdGuardManager

    if not dry_run and not Menu.prompt_for_change(
        f"Set AGH ports to dns={dns} http={http}",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)

    code = (
        AdGuardManager.create()
        .boot(install_override=install)
        .ports_set(dns=dns, http=http, dry_run=dry_run)
    )
    raise typer.Exit(code)


config_app = typer.Typer(name="config", help="Operations on AGH configuration.")
adguard_app.add_typer(config_app)


@config_app.command("validate")
def config_validate(
    install: Path = typer.Option(None, "--install"),
) -> None:
    """Run `AdGuardHome --check-config` and surface the result."""
    from .manager import AdGuardManager

    code = AdGuardManager.create().boot(install_override=install).config_validate()
    raise typer.Exit(code)


service_app = typer.Typer(name="service", help="Control the AdGuardHome systemd unit.")
adguard_app.add_typer(service_app)


@service_app.command("start")
def svc_start() -> None:
    """Start AdGuardHome.service."""
    from .manager import AdGuardManager

    raise typer.Exit(AdGuardManager.create().boot().service("start"))


@service_app.command("stop")
def svc_stop() -> None:
    """Stop AdGuardHome.service."""
    from .manager import AdGuardManager

    raise typer.Exit(AdGuardManager.create().boot().service("stop"))


@service_app.command("restart")
def svc_restart() -> None:
    """Restart AdGuardHome.service."""
    from .manager import AdGuardManager

    raise typer.Exit(AdGuardManager.create().boot().service("restart"))


@service_app.command("status")
def svc_status() -> None:
    """Print active/enabled/exists state for AdGuardHome.service."""
    from .manager import AdGuardManager

    raise typer.Exit(AdGuardManager.create().boot().service("status"))


@adguard_app.command("logs")
def logs(
    lines: int = typer.Option(80, "-n", "--lines", min=1, max=10000),
    follow: bool = typer.Option(False, "--follow", "-f"),
) -> None:
    """Tail journalctl -u AdGuardHome."""
    from .manager import AdGuardManager

    code = AdGuardManager.create().boot().logs(lines=lines, follow=follow)
    raise typer.Exit(code)


@adguard_app.command("rollback")
def rollback(
    install: Path = typer.Option(None, "--install"),
) -> None:
    """Restore the latest shimkit-managed yaml and /etc/resolv.conf backups."""
    from .manager import AdGuardManager

    code = AdGuardManager.create().boot(install_override=install).rollback()
    raise typer.Exit(code)
