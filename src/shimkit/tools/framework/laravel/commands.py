"""Typer subcommands for ``shimkit framework laravel``."""

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

laravel_app = typer.Typer(
    name="laravel",
    help="Laravel-specific helpers: perms, env scaffold, scheduler cron, artisan passthrough.",
    no_args_is_help=False,
)


@laravel_app.callback(invoke_without_command=True)
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
        UI.header("shimkit framework laravel")
        UI.line("Commands: perms / env / cron-install / artisan")


@laravel_app.command("perms")
def perms(
    project: Path = typer.Argument(..., help="Path to the Laravel project root."),
    group: str = typer.Option(
        None,
        "--group",
        help="Override the configured web group (default: tools.framework.laravel.web_group).",
    ),
    dry_run: bool = DRY_RUN,
    json_out: bool = JSON_OUT,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Fix Laravel storage + bootstrap/cache permissions. MODERATE prompt."""
    from .manager import LaravelManager

    if not dry_run and not Menu.prompt_for_change(
        f"Apply Laravel perms under {project}",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        LaravelManager.create()
        .boot()
        .perms(project, web_group=group, dry_run=dry_run, json_out=json_out)
    )
    raise typer.Exit(code)


@laravel_app.command("env")
def env_scaffold(
    project: Path = typer.Argument(..., help="Path to the Laravel project root."),
    app_name: str = typer.Option(None, "--name", help="APP_NAME (default: directory name)."),
    app_env: str = typer.Option("local", "--env", help="APP_ENV value."),
    db_engine: str = typer.Option(
        "mysql",
        "--db",
        help="Default DB connection (mysql/mariadb/postgres). Sets DB_CONNECTION + DB_PORT.",
    ),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Scaffold a starter .env with a generated APP_KEY. MODERATE prompt."""
    from .manager import LaravelManager

    if not dry_run and not Menu.prompt_for_change(
        f"Write {project / '.env'} (refuses to overwrite an existing file)",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        LaravelManager.create()
        .boot()
        .env_scaffold(
            project,
            app_name=app_name,
            app_env=app_env,
            db_engine=db_engine,
            dry_run=dry_run,
        )
    )
    raise typer.Exit(code)


@laravel_app.command("cron-install")
def cron_install(
    project: Path = typer.Argument(..., help="Path to the Laravel project root."),
    name: str = typer.Option(None, "--name", help="Cron entry name (default: laravel-<dirname>)."),
    schedule: str = typer.Option(
        None,
        "--schedule",
        help="Cron schedule (default: tools.framework.laravel.default_cron_schedule).",
    ),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Install a shimkit-managed cron entry for `php artisan schedule:run`. MODERATE prompt."""
    from .manager import LaravelManager

    if not dry_run and not Menu.prompt_for_change(
        f"Install Laravel scheduler cron entry for {project}",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        LaravelManager.create()
        .boot()
        .cron_install(project, name=name, schedule=schedule, dry_run=dry_run)
    )
    raise typer.Exit(code)


@laravel_app.command(
    "artisan",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def artisan(
    ctx: typer.Context,
    project: Path = typer.Option(
        Path.cwd, "--project", help="Project root (defaults to CWD)."
    ),
    in_container: bool = typer.Option(
        False,
        "--in-container",
        help="Run inside the shimkit stack lemp php-fpm container instead of on the host.",
    ),
    stack_project: str = typer.Option(
        None,
        "--stack",
        help="When --in-container, the stack project name (default: tools.stack.default_project).",
    ),
) -> None:
    """Run ``php artisan <args>`` (host by default; --in-container for stack lemp)."""
    from .manager import LaravelManager

    args = list(ctx.args)
    code = (
        LaravelManager.create()
        .boot()
        .artisan(
            project,
            args,
            in_container=in_container,
            stack_project=stack_project,
        )
    )
    raise typer.Exit(code)
