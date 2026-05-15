"""Typer subcommands for ``shimkit db``.

Surface:

    shimkit db ls                                # cross-engine
    shimkit db <engine> up [knobs]               # 5 engines
    shimkit db <engine> down
    shimkit db <engine> shell                    # interactive
    shimkit db <engine> dump [--out PATH]
    shimkit db <engine> reset --confirm RESET-DB # SEVERE
    shimkit db <engine> status [--json]
"""

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

from . import engines as _engines

db_app = typer.Typer(
    name="db",
    help="Container-first database orchestration (macOS + Linux).",
    no_args_is_help=False,
)


@db_app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    quiet: bool = QUIET,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
    no_color: bool = NO_COLOR,
    color: str = COLOR,
    no_input: bool = NO_INPUT,
) -> None:
    """Universal flags. Bare ``shimkit db`` prints the menu."""
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
        UI.header("shimkit db")
        UI.line("Engines: " + ", ".join(_engines.REGISTRY))
        UI.dim("Try: shimkit db ls  /  shimkit db mysql up  /  shimkit db --help")


@db_app.command("ls")
def ls(json_out: bool = JSON_OUT) -> None:
    """List shimkit-managed db containers."""
    from .manager import DbManager

    code = DbManager.create().boot().ls(json_out=json_out)
    raise typer.Exit(code)


# Per-engine sub-app builder — same shape for every engine.


def _register_engine(name: str) -> typer.Typer:
    """Create a Typer subapp for ``name`` with the shared command set."""
    app = typer.Typer(
        name=name,
        help=f"`{name}` container lifecycle.",
        no_args_is_help=False,
    )

    @app.callback(invoke_without_command=True)
    def _engine_root(ctx: typer.Context) -> None:
        if ctx.invoked_subcommand is None:
            UI.header(f"shimkit db {name}")
            UI.line("Commands: up / down / shell / dump / reset / status")

    @app.command("up")
    def up_cmd(
        id_: str = typer.Option(None, "--name", help="Per-engine instance id (default: 'dev')."),
        host_port: int = typer.Option(
            None, "--port", min=1, max=65535, help="Host port (default from config)."
        ),
        bind_host: str = typer.Option(
            None,
            "--bind",
            help="Host interface to bind to. Defaults to 127.0.0.1 (loopback-only).",
        ),
        volume: str = typer.Option(None, "--volume", help="Override the host data dir."),
        ephemeral: bool = typer.Option(
            False, "--ephemeral", help="No persistent volume (data lost on `down`)."
        ),
        password: str = typer.Option(
            None,
            "--password",
            help="Admin/root password. Default from config.",
        ),
        link_host: str = typer.Option(
            None,
            "--link-host",
            help="phpmyadmin only: backing-DB host (default host.docker.internal).",
        ),
        link_port: int = typer.Option(
            None,
            "--link-port",
            min=1,
            max=65535,
            help="phpmyadmin only: backing-DB port (default 13306).",
        ),
        on_host: bool = typer.Option(
            False,
            "--on-host",
            help="Manage an already-installed host engine via systemd/brew services "
            "instead of a container. Available on mysql/mariadb/postgres only.",
        ),
        json_out: bool = JSON_OUT,
        dry_run: bool = DRY_RUN,
        yes: bool = YES,
        force: bool = FORCE,
    ) -> None:
        from .manager import DbManager

        verb = "Start the host service for" if on_host else "Start a"
        if not dry_run and not Menu.prompt_for_change(
            f"{verb} {name}",
            yes=yes,
            force=force,
            no_input=UI.is_no_input(),
        ):
            UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
            raise typer.Exit(1)
        manager = DbManager.create().boot(force=force, on_host=on_host)
        bound = manager.for_engine(name)
        if on_host:
            code = bound.up_on_host(json_out=json_out, dry_run=dry_run)
        else:
            code = bound.up(
                id_=id_,
                host_port=host_port,
                bind_host=bind_host,
                volume=Path(volume).expanduser() if volume else None,
                ephemeral=ephemeral,
                password=password,
                link_host=link_host,
                link_port=link_port,
                json_out=json_out,
                dry_run=dry_run,
            )
        raise typer.Exit(code)

    @app.command("down")
    def down_cmd(
        id_: str = typer.Option(None, "--name"),
        on_host: bool = typer.Option(
            False,
            "--on-host",
            help="Stop the host service for this engine instead of a container.",
        ),
        json_out: bool = JSON_OUT,
        dry_run: bool = DRY_RUN,
        yes: bool = YES,
        force: bool = FORCE,
    ) -> None:
        from .manager import DbManager

        verb = "Stop the host service for" if on_host else "Stop + remove the"
        if not dry_run and not Menu.prompt_for_change(
            f"{verb} {name}{'' if on_host else ' container'}",
            yes=yes,
            force=force,
            no_input=UI.is_no_input(),
        ):
            UI.info("Cancelled. Pass --yes to skip the prompt or rerun with --dry-run.")
            raise typer.Exit(1)
        manager = DbManager.create().boot(force=force, on_host=on_host)
        bound = manager.for_engine(name)
        if on_host:
            code = bound.down_on_host(json_out=json_out, dry_run=dry_run)
        else:
            code = bound.down(id_=id_, json_out=json_out, dry_run=dry_run)
        raise typer.Exit(code)

    @app.command("shell")
    def shell_cmd(
        id_: str = typer.Option(None, "--name"),
        password: str = typer.Option(None, "--password"),
        on_host: bool = typer.Option(
            False,
            "--on-host",
            help="Connect via the host CLI to a host-installed engine instead "
            "of `docker exec` into a container.",
        ),
    ) -> None:
        from .manager import DbManager

        manager = DbManager.create().boot(on_host=on_host)
        bound = manager.for_engine(name)
        if on_host:
            code = bound.shell_on_host(password=password)
        else:
            code = bound.shell(id_=id_, password=password)
        raise typer.Exit(code)

    @app.command("dump")
    def dump_cmd(
        id_: str = typer.Option(None, "--name"),
        password: str = typer.Option(None, "--password"),
        out: str = typer.Option(None, "--out", help="Write dump to PATH instead of stdout."),
        json_out: bool = JSON_OUT,
    ) -> None:
        from .manager import DbManager

        code = (
            DbManager.create()
            .boot()
            .for_engine(name)
            .dump(
                id_=id_,
                password=password,
                out=Path(out).expanduser() if out else None,
                json_out=json_out,
            )
        )
        raise typer.Exit(code)

    @app.command("reset")
    def reset_cmd(
        id_: str = typer.Option(None, "--name"),
        confirm: str = typer.Option("", "--confirm", help="SEVERE token (see config)."),
        dry_run: bool = DRY_RUN,
    ) -> None:
        from shimkit.config import get_config

        from .manager import DbManager

        token = get_config().tools.db.reset_severe_token
        if not dry_run and confirm != token:
            UI.error(
                f"`reset` destroys the container AND its volume. "
                f"Pass `--confirm {token}` to proceed (SEVERE tier)."
            )
            raise typer.Exit(1)
        code = DbManager.create().boot().for_engine(name).reset(id_=id_, dry_run=dry_run)
        raise typer.Exit(code)

    @app.command("status")
    def status_cmd(
        id_: str = typer.Option(None, "--name"),
        on_host: bool = typer.Option(
            False,
            "--on-host",
            help="Report state of the host service instead of a container.",
        ),
        json_out: bool = JSON_OUT,
    ) -> None:
        from .manager import DbManager

        manager = DbManager.create().boot(on_host=on_host)
        bound = manager.for_engine(name)
        if on_host:
            code = bound.status_on_host(json_out=json_out)
        else:
            code = bound.status(id_=id_, json_out=json_out)
        raise typer.Exit(code)

    return app


# Register every engine as a sub-app under `shimkit db <engine>`.
for _name in _engines.REGISTRY:
    db_app.add_typer(_register_engine(_name))
