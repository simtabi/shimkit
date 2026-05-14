"""Shared Typer ``Option`` definitions for tool subcommands.

Every mutating command in shimkit's new tools accepts the same set of
flags (``--dry-run``, ``--json``, ``--quiet``, ``--verbose``, ``--yes``,
``--log-file``, ``--no-color``, ``--timeout``). Defining the options
once here keeps the surface consistent and the help text aligned across
commands.

Usage::

    @app.command("scan")
    def scan(
        dry_run: bool = DRY_RUN,
        json_out: bool = JSON_OUT,
        quiet: bool = QUIET,
        verbose: bool = VERBOSE,
    ) -> None:
        ...
"""

from __future__ import annotations

import typer

DRY_RUN = typer.Option(
    False,
    "--dry-run",
    "-n",
    help="Plan only; show what would happen, change nothing.",
)

JSON_OUT = typer.Option(
    False,
    "--json",
    help="Emit a single JSON document on stdout; suppress UI chatter.",
)

QUIET = typer.Option(
    False,
    "--quiet",
    "-q",
    help="Suppress non-error UI output. Errors still print.",
)

VERBOSE = typer.Option(
    False,
    "--verbose",
    "-v",
    help="Raise logger to DEBUG.",
)

YES = typer.Option(
    False,
    "--yes",
    "-y",
    help="Skip [y/N] confirmation prompts (severe ops still need --confirm).",
)

FORCE = typer.Option(
    False,
    "--force",
    "-f",
    help="Bypass safety checks. Logged loudly.",
)

LOG_FILE = typer.Option(
    None,
    "--log-file",
    help="Append JSONL events to PATH.",
    metavar="PATH",
)

NO_COLOR = typer.Option(
    False,
    "--no-color",
    help="Disable ANSI colour output (also honours NO_COLOR env).",
)

COLOR = typer.Option(
    None,
    "--color",
    help="Override the colour mode: auto, always, or never.",
    metavar="auto|always|never",
)

TIMEOUT = typer.Option(
    30.0,
    "--timeout",
    help="Seconds to wait for network / service operations.",
    min=1.0,
    max=600.0,
)

NO_INPUT = typer.Option(
    False,
    "--no-input",
    help="Never prompt; treat as non-interactive (set when stdin is not a TTY).",
)
