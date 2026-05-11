"""Typer subcommands for the shell tool."""

from __future__ import annotations

import typer

shell_app = typer.Typer(name="shell", help="Manage shell installations and upgrades.")


@shell_app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        from .manager import ShellManager

        ShellManager.create().boot().run()


@shell_app.command("info")
def info() -> None:
    """Print shell and package-manager information."""
    from .manager import ShellManager

    ShellManager.create().boot().info()


@shell_app.command("upgrade")
def upgrade(
    name: str = typer.Argument(..., help="bash | zsh | fish | ksh"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip the safety prompt when upgrading the currently active shell.",
    ),
) -> None:
    """Upgrade a shell via the host's package manager."""
    from .manager import ShellManager

    ok = ShellManager.create().boot().upgrade_shell(name, force=force)
    raise typer.Exit(0 if ok else 1)


@shell_app.command("simulate")
def simulate(name: str = typer.Argument(..., help="bash | zsh | fish | ksh")) -> None:
    """Print the commands shimkit would run, without executing them."""
    from .manager import ShellManager

    ShellManager.create().boot().simulate(name)
