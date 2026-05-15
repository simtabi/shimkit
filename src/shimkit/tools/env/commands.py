"""Typer subcommands for ``shimkit env``."""

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

env_app = typer.Typer(
    name="env",
    help="View / list / scaffold / diff / redact .env files with secret masking.",
    no_args_is_help=False,
)


def _maybe_path(p: str | None) -> Path | None:
    return Path(p).expanduser() if p else None


@env_app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    quiet: bool = QUIET,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
    no_color: bool = NO_COLOR,
    color: str = COLOR,
    no_input: bool = NO_INPUT,
) -> None:
    """Universal flags. Bare ``shimkit env`` opens the interactive menu."""
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
        from .manager import EnvManager

        EnvManager.create().boot().run()


@env_app.command("show")
def show(
    path: str = typer.Argument(
        None,
        help="Path to a .env file. If omitted, search cwd for the configured defaults.",
    ),
    reveal: bool = typer.Option(
        False, "--reveal", help="Show secret values verbatim. OFF by default."
    ),
    json_out: bool = JSON_OUT,
) -> None:
    """Print a .env file with secret values redacted (unless --reveal)."""
    from .manager import EnvManager

    code = EnvManager.create().boot().show(_maybe_path(path), reveal=reveal, json_out=json_out)
    raise typer.Exit(code)


@env_app.command("list")
def list_(
    root: str = typer.Argument(".", help="Directory to walk for .env* files."),
    json_out: bool = JSON_OUT,
) -> None:
    """List every .env* file under ROOT (default: cwd)."""
    from .manager import EnvManager

    code = EnvManager.create().boot().list_files(Path(root).expanduser(), json_out=json_out)
    raise typer.Exit(code)


@env_app.command("scaffold")
def scaffold(
    path: str = typer.Argument(..., help="Path to create (must not already exist)."),
    dry_run: bool = DRY_RUN,
) -> None:
    """Write a starter .env file at PATH. Refuses to overwrite."""
    from .manager import EnvManager

    code = EnvManager.create().boot().scaffold(Path(path).expanduser(), dry_run=dry_run)
    raise typer.Exit(code)


@env_app.command("diff")
def diff(
    a: str = typer.Argument(..., help="First .env file."),
    b: str = typer.Argument(..., help="Second .env file."),
    json_out: bool = JSON_OUT,
) -> None:
    """Show keys / values that differ between two .env files."""
    from .manager import EnvManager

    code = (
        EnvManager.create()
        .boot()
        .diff(Path(a).expanduser(), Path(b).expanduser(), json_out=json_out)
    )
    raise typer.Exit(code)


@env_app.command("redact")
def redact(
    src: str = typer.Argument(..., help="Source .env file."),
    dst: str = typer.Argument(..., help="Destination path (must not exist)."),
    dry_run: bool = DRY_RUN,
) -> None:
    """Write a redacted copy of SRC to DST (secrets masked)."""
    from .manager import EnvManager

    code = (
        EnvManager.create()
        .boot()
        .redact(
            Path(src).expanduser(),
            Path(dst).expanduser(),
            dry_run=dry_run,
        )
    )
    raise typer.Exit(code)
