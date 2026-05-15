"""Typer subcommands for ``shimkit gpg``."""

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

gpg_app = typer.Typer(
    name="gpg",
    help="GPG key + git-signing hygiene (macOS + Linux).",
    no_args_is_help=False,
)


@gpg_app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    quiet: bool = QUIET,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
    no_color: bool = NO_COLOR,
    color: str = COLOR,
    no_input: bool = NO_INPUT,
) -> None:
    """Universal flags. Bare ``shimkit gpg`` opens the interactive menu."""
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
        from .manager import GpgManager

        GpgManager.create().boot().run()


# ─── keys ──────────────────────────────────────────────────────────────

keys_app = typer.Typer(name="keys", help="List / generate / export GPG keys.")
gpg_app.add_typer(keys_app)


@keys_app.command("list")
def keys_list(json_out: bool = JSON_OUT) -> None:
    """List every primary key in your GPG keyring."""
    from .manager import GpgManager

    code = GpgManager.create().boot().keys_list(json_out=json_out)
    raise typer.Exit(code)


@keys_app.command("generate")
def keys_generate(
    name: str = typer.Argument(..., help="Real name for the new key's UID."),
    email: str = typer.Argument(..., help="Email for the new key's UID."),
    key_type: str = typer.Option(
        None, "--type", "-t", help="Key algorithm: ed25519 / rsa3072 / rsa4096."
    ),
    expiry: str = typer.Option(
        None, "--expiry", help="Expiry duration (gpg form: '1y', '6m', '0' for never)."
    ),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Generate a new GPG key. Passphrase prompted by gpg (not shimkit)."""
    from .manager import GpgManager

    if not dry_run and not Menu.prompt_for_change(
        f"Generate a new GPG key for {name} <{email}>",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        GpgManager.create()
        .boot()
        .keys_generate(
            name, email, key_type=key_type, expiry=expiry, dry_run=dry_run
        )
    )
    raise typer.Exit(code)


@keys_app.command("export")
def keys_export(
    key_id: str = typer.Argument(..., help="Key ID, fingerprint, or UID substring."),
    dest: str = typer.Option(
        None, "--dest", help="Write to PATH instead of stdout."
    ),
    dry_run: bool = DRY_RUN,
) -> None:
    """Export an ASCII-armoured public key."""
    from .manager import GpgManager

    dest_path = Path(dest).expanduser() if dest else None
    code = GpgManager.create().boot().keys_export(key_id, dest_path, dry_run=dry_run)
    raise typer.Exit(code)


# ─── agent ─────────────────────────────────────────────────────────────

agent_app = typer.Typer(name="agent", help="Inspect gpg-agent state.")
gpg_app.add_typer(agent_app)


@agent_app.command("status")
def agent_status(json_out: bool = JSON_OUT) -> None:
    """Check whether gpg-agent is responding."""
    from .manager import GpgManager

    code = GpgManager.create().boot().agent_status(json_out=json_out)
    raise typer.Exit(code)


# ─── git-signing ──────────────────────────────────────────────────────

git_signing_app = typer.Typer(
    name="git-signing", help="Inspect / configure git commit signing."
)
gpg_app.add_typer(git_signing_app)


@git_signing_app.command("show")
def git_signing_show(json_out: bool = JSON_OUT) -> None:
    """Show the current `user.signingkey` + `commit.gpgsign` config."""
    from .manager import GpgManager

    code = GpgManager.create().boot().git_signing_show(json_out=json_out)
    raise typer.Exit(code)


@git_signing_app.command("configure")
def git_signing_configure(
    key_id: str = typer.Argument(..., help="Key to use for signing commits."),
    scope: str = typer.Option(
        "global",
        "--scope",
        help="`global` (default) writes to ~/.gitconfig; `local` to the current repo.",
    ),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Set `user.signingkey` and turn on `commit.gpgsign`. MODERATE prompt."""
    from .manager import GpgManager

    if not dry_run and not Menu.prompt_for_change(
        f"Configure git ({scope}) to sign commits with {key_id}",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        GpgManager.create()
        .boot()
        .git_signing_configure(key_id, scope=scope, dry_run=dry_run)
    )
    raise typer.Exit(code)
