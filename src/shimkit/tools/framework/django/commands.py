"""Typer subcommands for ``shimkit framework django``."""

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

django_app = typer.Typer(
    name="django",
    help="Django-specific helpers: perms, .env scaffold, migrate, manage.py passthrough.",
    no_args_is_help=False,
)


@django_app.callback(invoke_without_command=True)
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
        UI.header("shimkit framework django")
        UI.line("Commands: perms / env / migrate / manage")


@django_app.command("perms")
def perms(
    project: Path = typer.Argument(..., help="Path to the Django project root."),
    group: str = typer.Option(
        None,
        "--group",
        help="Override the configured web group (default: tools.framework.django.web_group).",
    ),
    dry_run: bool = DRY_RUN,
    json_out: bool = JSON_OUT,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Fix Django media/ + staticfiles/ permissions. MODERATE prompt."""
    from .manager import DjangoManager

    if not dry_run and not Menu.prompt_for_change(
        f"Apply Django perms under {project}",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        DjangoManager.create()
        .boot()
        .perms(project, web_group=group, dry_run=dry_run, json_out=json_out)
    )
    raise typer.Exit(code)


@django_app.command("env")
def env_scaffold(
    project: Path = typer.Argument(..., help="Path to the Django project root."),
    app_name: str = typer.Option(None, "--name", help="App name (default: directory name)."),
    debug: bool = typer.Option(
        None,
        "--debug/--no-debug",
        help="DEBUG value (default: tools.framework.django.default_debug).",
    ),
    db_engine: str = typer.Option(
        "postgres",
        "--db",
        help="DATABASE_URL backend (postgres/mysql/mariadb). Targets shimkit db dev ports.",
    ),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Scaffold a starter .env with a generated SECRET_KEY. MODERATE prompt."""
    from .manager import DjangoManager

    if not dry_run and not Menu.prompt_for_change(
        f"Write {project / '.env'} (refuses to overwrite an existing file)",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        DjangoManager.create()
        .boot()
        .env_scaffold(
            project,
            app_name=app_name,
            debug=debug,
            db_engine=db_engine,
            dry_run=dry_run,
        )
    )
    raise typer.Exit(code)


@django_app.command("migrate")
def migrate(
    project: Path = typer.Argument(..., help="Path to the Django project root."),
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
    """Wraps `python manage.py migrate --no-input`."""
    from .manager import DjangoManager

    code = (
        DjangoManager.create()
        .boot()
        .migrate(
            project,
            in_container=in_container,
            stack_project=stack_project,
        )
    )
    raise typer.Exit(code)


@django_app.command(
    "manage",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def manage(
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
    """Run ``python manage.py <args>`` (host by default; --in-container for stack lemp)."""
    from .manager import DjangoManager

    args = list(ctx.args)
    code = (
        DjangoManager.create()
        .boot()
        .manage(
            project,
            args,
            in_container=in_container,
            stack_project=stack_project,
        )
    )
    raise typer.Exit(code)
