"""Typer subcommands for ``shimkit ssh``."""

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

ssh_app = typer.Typer(
    name="ssh",
    help="SSH key + agent + known_hosts + perms hygiene (macOS + Linux).",
    no_args_is_help=False,
)


def _ssh_override(p: str | None) -> Path | None:
    return Path(p).expanduser() if p else None


@ssh_app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    quiet: bool = QUIET,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
    no_color: bool = NO_COLOR,
    color: str = COLOR,
    no_input: bool = NO_INPUT,
) -> None:
    """Universal flags. Bare ``shimkit ssh`` opens the interactive menu."""
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
        from .manager import SshManager

        SshManager.create().boot().run()


# ─── keys ───────────────────────────────────────────────────────────────

keys_app = typer.Typer(name="keys", help="List / generate / rotate private keys.")
ssh_app.add_typer(keys_app)


@keys_app.command("list")
def keys_list(
    ssh_dir: str = typer.Option(None, "--ssh-dir"),
    json_out: bool = JSON_OUT,
) -> None:
    """List every recognised private key in the SSH directory."""
    from .manager import SshManager

    code = (
        SshManager.create()
        .boot(ssh_dir_override=_ssh_override(ssh_dir))
        .keys_list(json_out=json_out)
    )
    raise typer.Exit(code)


@keys_app.command("generate")
def keys_generate(
    name: str = typer.Argument(..., help="Filename for the new key (e.g. `id_ed25519`)."),
    key_type: str = typer.Option(
        None, "--type", "-t", help="Key type (default from config)."
    ),
    comment: str = typer.Option(None, "--comment", "-C"),
    ssh_dir: str = typer.Option(None, "--ssh-dir"),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Generate a new key pair via ``ssh-keygen``. Interactive passphrase."""
    from .manager import SshManager

    if not dry_run and not Menu.prompt_for_change(
        f"Generate a new SSH key at {name}",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        SshManager.create()
        .boot(ssh_dir_override=_ssh_override(ssh_dir))
        .keys_generate(name, key_type=key_type, comment=comment, dry_run=dry_run)
    )
    raise typer.Exit(code)


@keys_app.command("rotate")
def keys_rotate(
    name: str = typer.Argument(..., help="Existing key filename (e.g. `id_ed25519`)."),
    key_type: str = typer.Option(None, "--type", "-t"),
    ssh_dir: str = typer.Option(None, "--ssh-dir"),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Back up the old key and generate a new one with the same name."""
    from .manager import SshManager

    if not dry_run and not Menu.prompt_for_change(
        f"Rotate the key at {name} (old becomes .bak-*)",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        SshManager.create()
        .boot(ssh_dir_override=_ssh_override(ssh_dir))
        .keys_rotate(name, key_type=key_type, dry_run=dry_run)
    )
    raise typer.Exit(code)


# ─── agent ──────────────────────────────────────────────────────────────

agent_app = typer.Typer(name="agent", help="Inspect / load keys into ssh-agent.")
ssh_app.add_typer(agent_app)


@agent_app.command("status")
def agent_status(
    json_out: bool = JSON_OUT,
) -> None:
    """Show whether ssh-agent is running and which keys are loaded."""
    from .manager import SshManager

    code = SshManager.create().boot().agent_status(json_out=json_out)
    raise typer.Exit(code)


@agent_app.command("add")
def agent_add(
    key_path: str = typer.Argument(..., help="Path to the private key."),
    dry_run: bool = DRY_RUN,
) -> None:
    """Load a key into ssh-agent (passes through to `ssh-add`)."""
    from .manager import SshManager

    code = SshManager.create().boot().agent_add(Path(key_path).expanduser(), dry_run=dry_run)
    raise typer.Exit(code)


# ─── known_hosts ────────────────────────────────────────────────────────

known_hosts_app = typer.Typer(
    name="known-hosts", help="Audit / prune duplicate entries in known_hosts."
)
ssh_app.add_typer(known_hosts_app)


@known_hosts_app.command("audit")
def known_hosts_audit(
    ssh_dir: str = typer.Option(None, "--ssh-dir"),
    json_out: bool = JSON_OUT,
) -> None:
    """List duplicate entries in ~/.ssh/known_hosts."""
    from .manager import SshManager

    code = (
        SshManager.create()
        .boot(ssh_dir_override=_ssh_override(ssh_dir))
        .known_hosts_audit(json_out=json_out)
    )
    raise typer.Exit(code)


@known_hosts_app.command("prune")
def known_hosts_prune(
    ssh_dir: str = typer.Option(None, "--ssh-dir"),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """Remove later duplicates from ~/.ssh/known_hosts. MODERATE prompt."""
    from .manager import SshManager

    if not dry_run and not Menu.prompt_for_change(
        "Prune duplicate known_hosts entries",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        SshManager.create()
        .boot(ssh_dir_override=_ssh_override(ssh_dir))
        .known_hosts_prune(dry_run=dry_run)
    )
    raise typer.Exit(code)


# ─── perms ─────────────────────────────────────────────────────────────

perms_app = typer.Typer(name="perms", help="Audit / fix ~/.ssh permissions.")
ssh_app.add_typer(perms_app)


@perms_app.command("audit")
def perms_audit(
    ssh_dir: str = typer.Option(None, "--ssh-dir"),
    json_out: bool = JSON_OUT,
) -> None:
    """List every file/dir whose mode is laxer than the configured matrix."""
    from .manager import SshManager

    code = (
        SshManager.create()
        .boot(ssh_dir_override=_ssh_override(ssh_dir))
        .perms_audit(json_out=json_out)
    )
    raise typer.Exit(code)


@perms_app.command("fix")
def perms_fix(
    ssh_dir: str = typer.Option(None, "--ssh-dir"),
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """chmod every offender to its configured mode. MODERATE prompt."""
    from .manager import SshManager

    if not dry_run and not Menu.prompt_for_change(
        "Fix ~/.ssh permissions",
        yes=yes,
        force=force,
        no_input=UI.is_no_input(),
    ):
        UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
        raise typer.Exit(1)
    code = (
        SshManager.create()
        .boot(ssh_dir_override=_ssh_override(ssh_dir))
        .perms_fix(dry_run=dry_run)
    )
    raise typer.Exit(code)


# ─── config ────────────────────────────────────────────────────────────

config_app = typer.Typer(name="config", help="Inspect ~/.ssh/config.")
ssh_app.add_typer(config_app)


@config_app.command("show")
def config_show(
    host: str = typer.Argument(
        None, help="Optional host — expand the effective config via `ssh -G`."
    ),
    ssh_dir: str = typer.Option(None, "--ssh-dir"),
) -> None:
    """Print ~/.ssh/config; with HOST, show its expanded config."""
    from .manager import SshManager

    code = (
        SshManager.create()
        .boot(ssh_dir_override=_ssh_override(ssh_dir))
        .config_show(host)
    )
    raise typer.Exit(code)
