"""Typer subcommands for ``shimkit web nginx``."""

from __future__ import annotations

from pathlib import Path

import typer

from shimkit.core import UI, attach_file_handler, set_verbose
from shimkit.core.cli_flags import (
    COLOR,
    DRY_RUN,
    JSON_OUT,
    LOG_FILE,
    NO_COLOR,
    NO_INPUT,
    QUIET,
    VERBOSE,
)

nginx_app = typer.Typer(
    name="nginx",
    help="nginx vhost generator (file-only by default; opt-in apply).",
    no_args_is_help=False,
)


@nginx_app.callback(invoke_without_command=True)
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
        UI.header("shimkit web nginx")
        UI.line("Commands: vhost generate / apply / remove / list")


vhost_app = typer.Typer(name="vhost", help="vhost lifecycle.")
nginx_app.add_typer(vhost_app)


@vhost_app.command("generate")
def vhost_generate(
    name: str = typer.Option(..., "--name", help="Vhost file name (no path)."),
    domain: str = typer.Option(..., "--domain", help="Server name (e.g. foo.local)."),
    root: str = typer.Option(..., "--root", help="Document root on the server."),
    flavor: str = typer.Option(
        None,
        "--flavor",
        help="Template flavor: static / php / laravel (default from config).",
    ),
    php_version: str = typer.Option(
        None,
        "--php-version",
        help="PHP version for the fastcgi socket (default from config).",
    ),
    out: str = typer.Option(None, "--out", help="Write to PATH instead of stdout."),
    json_out: bool = JSON_OUT,
) -> None:
    """Render a hardened vhost. No host mutation."""
    from .manager import WebNginxManager

    code = (
        WebNginxManager.create()
        .boot()
        .generate(
            name=name,
            domain=domain,
            root=root,
            flavor=flavor,
            php_version=php_version,
            out=Path(out).expanduser() if out else None,
            json_out=json_out,
        )
    )
    raise typer.Exit(code)


@vhost_app.command("apply")
def vhost_apply(
    name: str = typer.Option(..., "--name", help="Vhost file name."),
    source: str = typer.Option(..., "--source", help="Path to the generated vhost file."),
    confirm: str = typer.Option("", "--confirm", help="SEVERE token."),
    dry_run: bool = DRY_RUN,
) -> None:
    """Install + enable + reload nginx. SEVERE — `--confirm APPLY-VHOST`."""
    from shimkit.config import get_config

    from .manager import WebNginxManager

    token = get_config().tools.web.nginx.apply_severe_token
    if not dry_run and confirm != token:
        UI.error(
            f"`apply` writes to /etc/nginx and reloads. "
            f"Pass `--confirm {token}` to proceed (SEVERE tier)."
        )
        raise typer.Exit(1)
    code = (
        WebNginxManager.create()
        .boot()
        .apply(
            name=name,
            source=Path(source).expanduser(),
            dry_run=dry_run,
        )
    )
    raise typer.Exit(code)


@vhost_app.command("remove")
def vhost_remove(
    name: str = typer.Option(..., "--name"),
    confirm: str = typer.Option("", "--confirm"),
    dry_run: bool = DRY_RUN,
) -> None:
    """Disable + remove a shimkit-managed vhost. SEVERE — `--confirm REMOVE-VHOST`."""
    from shimkit.config import get_config

    from .manager import WebNginxManager

    token = get_config().tools.web.nginx.remove_severe_token
    if not dry_run and confirm != token:
        UI.error(
            f"`remove` deletes from /etc/nginx and reloads. "
            f"Pass `--confirm {token}` to proceed (SEVERE tier)."
        )
        raise typer.Exit(1)
    code = WebNginxManager.create().boot().remove(name=name, dry_run=dry_run)
    raise typer.Exit(code)


@vhost_app.command("list")
def vhost_list(json_out: bool = JSON_OUT) -> None:
    """List vhosts enabled at `sites-enabled/`; flag which shimkit manages."""
    from .manager import WebNginxManager

    code = WebNginxManager.create().boot().list_vhosts(json_out=json_out)
    raise typer.Exit(code)
