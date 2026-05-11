"""Typer subcommand surface for the Java tool.

``shimkit java`` (no args) runs the interactive menu — preserves the
legacy java-update-manager UX. Subcommands (``install``, ``list``, …)
call non-interactive methods on JavaManager and return shell exit codes.
"""

from __future__ import annotations

import typer

java_app = typer.Typer(name="java", help="Manage OpenJDK installations.")


@java_app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        from .manager import JavaManager

        JavaManager.create().boot().run()


@java_app.command("install")
def install(
    version: str = typer.Argument(
        None,
        help="Major version, e.g. 21. Defaults to config.tools.java.default_version.",
    ),
) -> None:
    """Install a Java version via Homebrew."""
    from shimkit.config import get_config

    from .manager import JavaManager

    if version is None:
        version = str(get_config().tools.java.default_version)
    ok = JavaManager.create().boot().install(version)
    raise typer.Exit(0 if ok else 1)


@java_app.command("list")
def list_versions() -> None:
    """List all discovered Java installations."""
    from shimkit.core import UI

    from .manager import JavaManager

    installs = JavaManager.create().boot().list_installations()
    if not installs:
        UI.info("No Java installations found.")
        return
    for inst in installs:
        tick = "✓" if inst.active else " "
        UI.info(f"  {tick} [{inst.kind}] {inst.version}")
        UI.dim(f"      {inst.path}")


@java_app.command("switch")
def switch(version: str = typer.Argument(..., help="Major version to make active")) -> None:
    """Switch the active Java version."""
    from shimkit.core import UI

    from .manager import JavaManager

    if JavaManager.create().boot().switch_active(version):
        UI.success(f"Switched to openjdk@{version}.")
        raise typer.Exit(0)
    UI.error(f"Failed to switch to openjdk@{version}.")
    raise typer.Exit(1)


@java_app.command("upgrade")
def upgrade(
    version: str = typer.Argument(
        None, help="Specific major version; omit to upgrade every outdated openjdk@*"
    ),
) -> None:
    """Upgrade an installed Java version (or all outdated versions)."""
    from .manager import JavaManager

    ok = JavaManager.create().boot().upgrade(version)
    raise typer.Exit(0 if ok else 1)


@java_app.command("uninstall")
def uninstall(version: str = typer.Argument(..., help="Major version to remove")) -> None:
    """Uninstall a Java version."""
    from .manager import JavaManager

    ok = JavaManager.create().boot().uninstall(version)
    raise typer.Exit(0 if ok else 1)


@java_app.command("remove-oracle")
def remove_oracle() -> None:
    """Remove Oracle JDK and related components (macOS only)."""
    from shimkit.core import UI

    from .manager import JavaManager

    if JavaManager.create().boot().remove_oracle():
        UI.success("Oracle Java removed.")
        raise typer.Exit(0)
    UI.warning("Nothing was removed.")
    raise typer.Exit(1)
