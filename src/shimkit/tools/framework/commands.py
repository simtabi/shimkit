"""Typer parent app for ``shimkit framework``.

Today there's one child (``laravel``); future siblings (``symfony``,
``rails``, ``django``, ``nextjs``) slot in under the same parent
without disturbing the existing surface.
"""

from __future__ import annotations

import typer

from shimkit.core import UI

from .laravel.commands import laravel_app

framework_app = typer.Typer(
    name="framework",
    help="Framework-specific helpers (Laravel today; more recipes welcome).",
    no_args_is_help=False,
)

framework_app.add_typer(laravel_app)


@framework_app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        UI.header("shimkit framework")
        UI.line("Frameworks: laravel")
        UI.line("Run `shimkit framework laravel --help` for details.")
