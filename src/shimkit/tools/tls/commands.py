"""Typer subcommands for ``shimkit tls``."""

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

tls_app = typer.Typer(
    name="tls",
    help="TLS cert lifecycle helper via container-first certbot.",
    no_args_is_help=False,
)


@tls_app.callback(invoke_without_command=True)
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
        UI.header("shimkit tls")
        UI.line("Commands: request / list / status / renew / revoke / cron-install")


@tls_app.command("request")
def request(
    domain: list[str] = typer.Option(
        ..., "--domain", "-d", help="Domain to request a cert for (repeat for SAN)."
    ),
    email: str = typer.Option(
        None,
        "--email",
        help="ACME account email (default: tools.tls.default_email).",
    ),
    method: str = typer.Option(
        "webroot",
        "--method",
        help="ACME challenge method: webroot (default, HTTP-01) or "
        "dns-cloudflare (DNS-01; required for wildcard certs).",
    ),
    webroot: Path = typer.Option(
        None,
        "--webroot",
        help="Local webroot served at /.well-known/acme-challenge/ "
        "(webroot method only).",
    ),
    credentials: Path = typer.Option(
        None,
        "--credentials",
        help="Path to a Cloudflare credentials file (mode 0600). "
        "Format: `dns_cloudflare_api_token = <token>`. "
        "(dns-cloudflare method only).",
    ),
    staging: bool = typer.Option(
        False,
        "--staging",
        help="Use the Let's Encrypt staging CA (recommended for first runs).",
    ),
    dry_run: bool = DRY_RUN,
    json_out: bool = JSON_OUT,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Request a new TLS cert via certbot. MODERATE prompt.

    Two challenge methods supported:

    - ``--method webroot`` (default, HTTP-01) — requires nginx (or
      any webserver) to be serving the webroot at
      ``/.well-known/acme-challenge/``.
    - ``--method dns-cloudflare`` (DNS-01) — required for wildcard
      certs (``*.example.com``). Requires a Cloudflare API token
      with `Zone:DNS:Edit` scope on the zone.
    """
    from .manager import TlsManager

    method_label = f" via {method}" if method != "webroot" else ""
    summary = f"Request cert for {', '.join(domain)}{method_label}"
    if not dry_run and not Menu.prompt_for_change(
        summary,
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        TlsManager.create()
        .boot()
        .request(
            domains=list(domain),
            email=email,
            webroot=webroot,
            credentials=credentials,
            method=method,  # type: ignore[arg-type]
            staging=staging,
            dry_run=dry_run,
            json_out=json_out,
        )
    )
    raise typer.Exit(code)


@tls_app.command("list")
def list_certs(json_out: bool = JSON_OUT) -> None:
    """List local certs with expiry dates."""
    from .manager import TlsManager

    code = TlsManager.create().boot().list_certs(json_out=json_out)
    raise typer.Exit(code)


@tls_app.command("status")
def status(
    domain: str = typer.Argument(..., help="Domain to report status for."),
    json_out: bool = JSON_OUT,
) -> None:
    """Show a single cert's paths and expiry."""
    from .manager import TlsManager

    code = TlsManager.create().boot().status(domain=domain, json_out=json_out)
    raise typer.Exit(code)


@tls_app.command("renew")
def renew(
    domain: str = typer.Option(
        None, "--domain", "-d", help="Renew only this cert (default: all due)."
    ),
    force: bool = typer.Option(
        False,
        "--force-renewal",
        help="Force renewal even when the cert isn't near expiry.",
    ),
    dry_run: bool = DRY_RUN,
    json_out: bool = JSON_OUT,
    yes: bool = YES,
    force_prompt: bool = FORCE,
) -> None:
    """Renew certs (all due, or one named). MODERATE prompt."""
    from .manager import TlsManager

    summary = f"Renew cert(s) {'for ' + domain if domain else '(all due)'}"
    if not dry_run and not Menu.prompt_for_change(
        summary,
        yes=yes,
        force=force_prompt,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        TlsManager.create()
        .boot()
        .renew(
            domain=domain,
            force=force,
            dry_run=dry_run,
            json_out=json_out,
        )
    )
    raise typer.Exit(code)


@tls_app.command("revoke")
def revoke(
    domain: str = typer.Option(..., "--domain", "-d", help="Domain to revoke."),
    confirm: str = typer.Option(
        None, "--confirm", help="Required severe-token from `tools.tls.revoke_severe_token`."
    ),
    dry_run: bool = DRY_RUN,
    json_out: bool = JSON_OUT,
) -> None:
    """Revoke a cert via the ACME CA. SEVERE — requires `--confirm REVOKE-TLS`."""
    from shimkit.config import get_config

    from .manager import TlsManager

    expected = get_config().tools.tls.revoke_severe_token
    if not dry_run and confirm != expected:
        UI.error(f"Revoke is SEVERE; pass `--confirm {expected}` to proceed.")
        raise typer.Exit(1)
    code = (
        TlsManager.create()
        .boot()
        .revoke(domain=domain, dry_run=dry_run, json_out=json_out)
    )
    raise typer.Exit(code)


@tls_app.command("cron-install")
def cron_install(
    schedule: str = typer.Option(
        None,
        "--schedule",
        help="Cron schedule (default: tools.tls.renewal_schedule).",
    ),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Install a daily `shimkit tls renew` cron entry. MODERATE prompt."""
    from .manager import TlsManager

    if not dry_run and not Menu.prompt_for_change(
        "Install daily TLS renewal cron entry",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        TlsManager.create()
        .boot()
        .cron_install(schedule=schedule, dry_run=dry_run)
    )
    raise typer.Exit(code)
