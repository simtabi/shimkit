"""Parent Typer subapp for ``shimkit web *``."""

from __future__ import annotations

import typer

from shimkit.core import UI

from .nginx.commands import nginx_app

web_app = typer.Typer(
    name="web",
    help="Web-server tooling (nginx today; caddy/apache/tls candidates).",
    no_args_is_help=False,
)

web_app.add_typer(nginx_app)


@web_app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        UI.header("shimkit web")
        UI.line("Tools: nginx")
        UI.dim("Try: shimkit web nginx vhost generate --help")
