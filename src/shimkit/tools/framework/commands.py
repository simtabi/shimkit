"""Typer parent app for ``shimkit framework``.

Today: ``laravel`` (v0.7.0), ``symfony`` (v0.14.0), ``django``
(v0.16.0). Future siblings (``rails``, ``nextjs``) slot in under
the same parent without disturbing the existing surface.
"""

from __future__ import annotations

import typer

from shimkit.core import UI

from .django.commands import django_app
from .laravel.commands import laravel_app
from .symfony.commands import symfony_app

framework_app = typer.Typer(
    name="framework",
    help="Framework-specific helpers (Laravel + Symfony + Django; more recipes welcome).",
    no_args_is_help=False,
)

framework_app.add_typer(laravel_app)
framework_app.add_typer(symfony_app)
framework_app.add_typer(django_app)


@framework_app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        UI.header("shimkit framework")
        UI.line("Frameworks: laravel, symfony, django")
        UI.line("Run `shimkit framework <name> --help` for details.")
