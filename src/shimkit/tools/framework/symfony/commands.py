"""Typer subcommands for ``shimkit framework symfony``."""

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

symfony_app = typer.Typer(
    name="symfony",
    help="Symfony-specific helpers: perms, .env.local scaffold, cache-clear, console passthrough.",
    no_args_is_help=False,
)


@symfony_app.callback(invoke_without_command=True)
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
        UI.header("shimkit framework symfony")
        UI.line("Commands: perms / env / cache-clear / console")


@symfony_app.command("perms")
def perms(
    project: Path = typer.Argument(..., help="Path to the Symfony project root."),
    group: str = typer.Option(
        None,
        "--group",
        help="Override the configured web group (default: tools.framework.symfony.web_group).",
    ),
    dry_run: bool = DRY_RUN,
    json_out: bool = JSON_OUT,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Fix Symfony var/ permissions. MODERATE prompt."""
    from .manager import SymfonyManager

    if not dry_run and not Menu.prompt_for_change(
        f"Apply Symfony perms under {project}",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        SymfonyManager.create()
        .boot()
        .perms(project, web_group=group, dry_run=dry_run, json_out=json_out)
    )
    raise typer.Exit(code)


@symfony_app.command("env")
def env_scaffold(
    project: Path = typer.Argument(..., help="Path to the Symfony project root."),
    app_name: str = typer.Option(None, "--name", help="App name (default: directory name)."),
    app_env: str = typer.Option(
        None, "--env", help="APP_ENV value (default: tools.framework.symfony.default_env)."
    ),
    db_engine: str = typer.Option(
        "mysql",
        "--db",
        help="DATABASE_URL backend (mysql/mariadb/postgres). Targets shimkit db dev ports.",
    ),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Scaffold a starter .env.local with a generated APP_SECRET. MODERATE prompt."""
    from .manager import SymfonyManager

    if not dry_run and not Menu.prompt_for_change(
        f"Write {project / '.env.local'} (refuses to overwrite an existing file)",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        SymfonyManager.create()
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


@symfony_app.command("cache-clear")
def cache_clear(
    project: Path = typer.Argument(..., help="Path to the Symfony project root."),
    app_env: str = typer.Option(
        None, "--env", help="--env to pass to bin/console cache:clear (default: dev)."
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
    """Wraps `php bin/console cache:clear --env <env>`."""
    from .manager import SymfonyManager

    code = (
        SymfonyManager.create()
        .boot()
        .cache_clear(
            project,
            app_env=app_env,
            in_container=in_container,
            stack_project=stack_project,
        )
    )
    raise typer.Exit(code)


@symfony_app.command(
    "console",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def console(
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
    """Run ``php bin/console <args>`` (host by default; --in-container for stack lemp)."""
    from .manager import SymfonyManager

    args = list(ctx.args)
    code = (
        SymfonyManager.create()
        .boot()
        .console(
            project,
            args,
            in_container=in_container,
            stack_project=stack_project,
        )
    )
    raise typer.Exit(code)
