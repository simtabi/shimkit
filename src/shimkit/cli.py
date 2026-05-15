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
from shimkit.core import UI
from shimkit.tools.adguard.commands import adguard_app
from shimkit.tools.dns.commands import dns_app
from shimkit.tools.docker_clean.commands import docker_clean_app
from shimkit.tools.env.commands import env_app
from shimkit.tools.gpg.commands import gpg_app
from shimkit.tools.hosts.commands import hosts_app
from shimkit.tools.java.commands import java_app
from shimkit.tools.logs.commands import logs_app
from shimkit.tools.ports.commands import ports_app
from shimkit.tools.shell.commands import shell_app
from shimkit.tools.ssh.commands import ssh_app

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
app.add_typer(dns_app)
app.add_typer(adguard_app)
app.add_typer(docker_clean_app)
app.add_typer(ports_app)
app.add_typer(hosts_app)
app.add_typer(ssh_app)
app.add_typer(env_app)
app.add_typer(gpg_app)
app.add_typer(logs_app)


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
        UI.error(str(exc))
        raise typer.Exit(1) from exc

    data: object = cfg.model_dump(mode="json")
    if section:
        for part in section.split("."):
            if not isinstance(data, dict) or part not in data:
                UI.error(f"No such config key: {section}")
                raise typer.Exit(1)
            data = data[part]
    UI.line(_json.dumps(data, indent=2, ensure_ascii=False))


@config_app.command("path")
def config_path() -> None:
    """Print the resolved user-override config path."""
    from shimkit.config import bundled_defaults_path, user_config_path

    user = user_config_path()
    UI.line(f"defaults: {bundled_defaults_path()}")
    UI.line(f"user:     {user}  ({'exists' if user.exists() else 'missing'})")


@config_app.command("edit")
def config_edit() -> None:
    """Open the user override config in $EDITOR (creates from template if missing)."""
    import os as _os

    from shimkit.config import user_config_path
    from shimkit.core import CommandRunner

    path = user_config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_user_config_template(), encoding="utf-8")
        UI.line(f"Created template at {path}")
    editor = _os.environ.get("EDITOR") or _os.environ.get("VISUAL") or "vi"
    # capture_output=False so the editor inherits the parent's stdin/stdout/stderr.
    result = CommandRunner.run([editor, str(path)], capture_output=False)
    raise typer.Exit(result.returncode)


@config_app.command("validate")
def config_validate() -> None:
    """Validate defaults + user overrides against the schema.

    Exits 78 (EX_CONFIG, sysexits.h) when validation fails — distinct
    from generic 1 so scripts can detect "config is broken" vs other
    failures.
    """
    from shimkit.config import ConfigError, load

    try:
        load()
    except ConfigError as exc:
        UI.error(str(exc))
        raise typer.Exit(78) from exc
    UI.success("Configuration is valid.")


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

    UI.line(f"shimkit  {__version__}")
    UI.line(f"python   {sys.version.split()[0]} ({sys.executable})")
    UI.line(f"system   {_plat.system()} {_plat.release()} {_plat.machine()}")

    plat = Platform.detect()
    sh = Shell.detect(plat)
    UI.line(f"platform {plat.description}")
    UI.line(f"shell    {sh.description}")

    pm = PackageManager.detect(plat)
    UI.line(f"pm       {pm.name if pm else '<none detected>'}")
    UI.line(f"brew     {_shutil.which('brew') or '<not found>'}")

    UI.line(f"defaults {bundled_defaults_path()}")
    user = user_config_path()
    UI.line(f"user cfg {user}  ({'exists' if user.exists() else 'missing'})")
    try:
        load()
        UI.line("config   valid")
    except ConfigError as exc:
        UI.line(f"config   INVALID — {str(exc).splitlines()[0]}")

    method = _detect_shimkit_install_method()
    UI.line(f"installed via  {method or '<unknown>'}")

    # --- per-tool probes for the three new tools --------------------
    if plat.is_macos:
        try:
            from shimkit.tools.dns import scutil

            chain = scutil.query()
            top = ",".join(chain.primary_nameservers) or "(none)"
            UI.line(f"dns probe      {len(chain.resolvers)} resolver(s); top: {top}")
        except Exception as exc:
            UI.line(f"dns probe      ERROR — {exc}")

    if plat.is_linux:
        try:
            from shimkit.tools.adguard import finder

            install = finder.detect()
            UI.line(f"adguard        {install.binary if install else '<absent>'}")
        except Exception as exc:
            UI.line(f"adguard        ERROR — {exc}")

    # docker probe — shell out via CommandRunner instead of docker-py.
    # The subprocess approach avoids docker-py's urllib3 connection-pool
    # fds lingering past close() and triggering pytest's unraisable-
    # exception warnings on Python 3.12+. Also means the probe works
    # without the `[docker-clean]` extra installed.
    try:
        from shimkit.core import CommandRunner

        if _shutil.which("docker") is None:
            UI.line("docker         <not installed>")
        else:
            r = CommandRunner.run(["docker", "version", "--format", "{{.Server.Version}}"])
            ver = r.stdout.strip()
            if r.ok and ver:
                UI.line(f"docker         {ver}")
            else:
                UI.line("docker         <not running>")
    except Exception as exc:
        UI.line(f"docker         ERROR — {exc}")

    # --- version constraints audit ------------------------------------
    from shimkit.core import version as _vc

    UI.line("")
    UI.line("versions")
    for vr in _vc.validate_all():
        name = vr.tool.ljust(10)
        if vr.status is _vc.Status.OK:
            ver = vr.tool_version.raw if vr.tool_version else "?"
            UI.line(f"  {name} {ver.ljust(10)} ok")
            continue
        if vr.status is _vc.Status.OUT_OF_RANGE:
            ver = vr.tool_version.raw if vr.tool_version else "?"
            spec: list[str] = []
            if vr.constraint.min:
                spec.append(f"min={vr.constraint.min}")
            if vr.constraint.max:
                spec.append(f"max={vr.constraint.max}")
            UI.line(f"  {name} {ver.ljust(10)} OUT-OF-RANGE  ({', '.join(spec)})")
            if vr.remediation:
                UI.dim(f"    → {vr.remediation}")
            continue
        if vr.status is _vc.Status.MISSING:
            UI.line(f"  {name} <missing>  not on PATH")
            if vr.remediation:
                UI.dim(f"    → {vr.remediation}")
            continue
        if vr.status is _vc.Status.UNPARSEABLE:
            raw = vr.tool_version.raw if vr.tool_version else "?"
            UI.line(f"  {name} {raw.ljust(10)} UNPARSEABLE (output didn't match)")


def _detect_shimkit_install_method() -> str | None:
    """Cheap install-method probe for `doctor` (separate from self_update.run)."""
    from shimkit.self_update import _detect_install_method

    return _detect_install_method()


@app.command("self-update")
def self_update(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Update shimkit itself to the latest release."""
    from shimkit import self_update as _su

    raise typer.Exit(_su.run(yes=yes))


@app.command("version")
def version() -> None:
    """Print the shimkit version."""
    UI.line(__version__)


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    """Print help when called bare. Per-tool menus live under each subcommand."""
    if ctx.invoked_subcommand is None:
        UI.line(ctx.get_help())


if __name__ == "__main__":
    app()
