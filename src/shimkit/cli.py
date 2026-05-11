"""Top-level Typer dispatcher.

Subcommand surface is composed from per-tool Typer apps so each tool owns
its own command tree. The bare ``shimkit`` invocation prints help —
each tool's bare invocation (e.g. ``shimkit java``) drops into that
tool's interactive menu.
"""

from __future__ import annotations

import sys

import typer

from shimkit import __version__
from shimkit.tools.java.commands import java_app
from shimkit.tools.shell.commands import shell_app

app = typer.Typer(
    name="shimkit",
    help="A toolkit of developer utilities. Python tools, shimmed by bash.",
    no_args_is_help=False,
    add_completion=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)

app.add_typer(java_app)
app.add_typer(shell_app)


# --- config -----------------------------------------------------------------

config_app = typer.Typer(name="config", help="Inspect and edit shimkit configuration.")
app.add_typer(config_app)


@config_app.command("show")
def config_show(
    section: str = typer.Argument(
        None, help="Optional dotted path, e.g. 'tools.java' or 'ui.color'."
    ),
) -> None:
    """Print the resolved configuration as JSON."""
    import json as _json

    from shimkit.config import ConfigError, load

    try:
        cfg = load()
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    data: object = cfg.model_dump(mode="json")
    if section:
        for part in section.split("."):
            if not isinstance(data, dict) or part not in data:
                typer.secho(
                    f"No such config key: {section}", fg=typer.colors.RED, err=True
                )
                raise typer.Exit(1)
            data = data[part]
    typer.echo(_json.dumps(data, indent=2, ensure_ascii=False))


@config_app.command("path")
def config_path() -> None:
    """Print the resolved user-override config path."""
    from shimkit.config import bundled_defaults_path, user_config_path

    user = user_config_path()
    typer.echo(f"defaults: {bundled_defaults_path()}")
    typer.echo(f"user:     {user}  ({'exists' if user.exists() else 'missing'})")


@config_app.command("edit")
def config_edit() -> None:
    """Open the user override config in $EDITOR (creates from template if missing)."""
    import os as _os
    import subprocess

    from shimkit.config import user_config_path

    path = user_config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_user_config_template(), encoding="utf-8")
        typer.echo(f"Created template at {path}")
    editor = _os.environ.get("EDITOR") or _os.environ.get("VISUAL") or "vi"
    raise typer.Exit(subprocess.call([editor, str(path)]))


@config_app.command("validate")
def config_validate() -> None:
    """Validate defaults + user overrides against the schema."""
    from shimkit.config import ConfigError, load

    try:
        load()
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    typer.secho("Configuration is valid.", fg=typer.colors.GREEN)


def _user_config_template() -> str:
    """Return the empty-but-annotated template for first-time `config edit`."""
    return (
        "{\n"
        '  "$schema": "https://raw.githubusercontent.com/simtabi/shimkit/main/'
        'config/shimkit.schema.json",\n'
        '  "schema_version": 1\n'
        "}\n"
    )


# --- top-level commands ----------------------------------------------------


@app.command("doctor")
def doctor() -> None:
    """Print system diagnostics useful for bug reports."""
    import platform as _plat
    import shutil as _shutil

    from shimkit.config import (
        ConfigError,
        bundled_defaults_path,
        load,
        user_config_path,
    )
    from shimkit.core import PackageManager, Platform, Shell

    typer.echo(f"shimkit  {__version__}")
    typer.echo(f"python   {sys.version.split()[0]} ({sys.executable})")
    typer.echo(f"system   {_plat.system()} {_plat.release()} {_plat.machine()}")

    plat = Platform.detect()
    sh = Shell.detect(plat)
    typer.echo(f"platform {plat.description}")
    typer.echo(f"shell    {sh.description}")

    pm = PackageManager.detect(plat)
    typer.echo(f"pm       {pm.name if pm else '<none detected>'}")
    typer.echo(f"brew     {_shutil.which('brew') or '<not found>'}")

    typer.echo(f"defaults {bundled_defaults_path()}")
    user = user_config_path()
    typer.echo(f"user cfg {user}  ({'exists' if user.exists() else 'missing'})")
    try:
        load()
        typer.echo("config   valid")
    except ConfigError as exc:
        typer.echo(f"config   INVALID — {str(exc).splitlines()[0]}")

    method = _detect_shimkit_install_method()
    typer.echo(f"installed via  {method or '<unknown>'}")


def _detect_shimkit_install_method() -> str | None:
    """Cheap install-method probe for `doctor` (separate from self_update.run)."""
    from shimkit.self_update import _detect_install_method

    return _detect_install_method()


@app.command("self-update")
def self_update(
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt."
    ),
) -> None:
    """Update shimkit itself to the latest release."""
    from shimkit import self_update as _su

    raise typer.Exit(_su.run(yes=yes))


@app.command("version")
def version() -> None:
    """Print the shimkit version."""
    typer.echo(__version__)


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    """Print help when called bare. Per-tool menus live under each subcommand."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


if __name__ == "__main__":
    app()
