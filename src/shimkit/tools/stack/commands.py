"""Typer subcommands for ``shimkit stack``."""

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

stack_app = typer.Typer(
    name="stack",
    help="Multi-container app recipes (LEMP today; MERN/Rails/MEAN later).",
    no_args_is_help=False,
)


@stack_app.callback(invoke_without_command=True)
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
        UI.header("shimkit stack")
        UI.line("Recipes: lemp")
        UI.dim("Try: shimkit stack ls / shimkit stack lemp up / shimkit stack lemp --help")


@stack_app.command("ls")
def ls(json_out: bool = JSON_OUT) -> None:
    """List shimkit-managed stack projects."""
    from .manager import StackManager

    code = StackManager.create().boot().ls(json_out=json_out)
    raise typer.Exit(code)


# ── lemp recipe ────────────────────────────────────────────────────────

lemp_app = typer.Typer(name="lemp", help="LEMP recipe (db + php-fpm + nginx).")
stack_app.add_typer(lemp_app)


@lemp_app.callback(invoke_without_command=True)
def _lemp_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        UI.header("shimkit stack lemp")
        UI.line("Commands: up / down / status / logs / exec")


@lemp_app.command("up")
def lemp_up(
    project: str = typer.Option(None, "--project", help="Project id (default: shimkit-dev)."),
    db_engine: str = typer.Option(
        None, "--db", help="Database engine: mysql / mariadb / postgres (default mysql)."
    ),
    host_port: int = typer.Option(
        None, "--port", min=1, max=65535, help="Host port for nginx (default 18080)."
    ),
    project_root: str = typer.Option(
        None,
        "--project-root",
        help="Path bind-mounted at /srv/app inside containers (default: cwd).",
    ),
    password: str = typer.Option(None, "--password", help="DB admin password."),
    json_out: bool = JSON_OUT,
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Bring up a LEMP stack (db + php-fpm + nginx). Idempotent."""
    from .manager import StackManager

    if not dry_run and not Menu.prompt_for_change(
        "Bring up a LEMP stack (3 containers + 1 network)",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        StackManager.create()
        .boot(force=force)
        .lemp()
        .up(
            project=project,
            db_engine=db_engine,
            host_port=host_port,
            project_root=Path(project_root) if project_root else None,
            password=password,
            json_out=json_out,
            dry_run=dry_run,
        )
    )
    raise typer.Exit(code)


@lemp_app.command("down")
def lemp_down(
    project: str = typer.Option(None, "--project"),
    json_out: bool = JSON_OUT,
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Tear down a LEMP stack."""
    from .manager import StackManager

    if not dry_run and not Menu.prompt_for_change(
        "Tear down the LEMP stack",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        StackManager.create()
        .boot(force=force)
        .lemp()
        .down(project=project, json_out=json_out, dry_run=dry_run)
    )
    raise typer.Exit(code)


@lemp_app.command("status")
def lemp_status(
    project: str = typer.Option(None, "--project"),
    json_out: bool = JSON_OUT,
) -> None:
    """Report each container's state."""
    from .manager import StackManager

    code = StackManager.create().boot().lemp().status(project=project, json_out=json_out)
    raise typer.Exit(code)


@lemp_app.command("logs")
def lemp_logs(
    project: str = typer.Option(None, "--project"),
    follow: bool = typer.Option(False, "--follow", "-f"),
    tail: int = typer.Option(100, "--tail", min=1, max=100_000),
) -> None:
    """Print recent logs from each container."""
    from .manager import StackManager

    code = StackManager.create().boot().lemp().logs(project=project, follow=follow, tail=tail)
    raise typer.Exit(code)


@lemp_app.command("exec")
def lemp_exec(
    cmd: list[str] = typer.Argument(..., help="Command + args to run in the php-fpm container."),
    project: str = typer.Option(None, "--project"),
) -> None:
    """Run a command inside the project's php-fpm container.

    Example: ``shimkit stack lemp exec -- php artisan migrate``
    """
    from .manager import StackManager

    code = StackManager.create().boot().lemp().exec_(cmd=cmd, project=project)
    raise typer.Exit(code)
