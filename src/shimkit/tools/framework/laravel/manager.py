"""LaravelManager -- orchestrator for ``shimkit framework laravel``.

Pure-host operations (perms, env scaffold) shell out via
``CommandRunner``. ``cron-install`` delegates to
:class:`shimkit.tools.cron.CronManager`. ``artisan`` runs on the
host by default; ``--in-container`` routes through
:class:`shimkit.tools.stack.StackManager`'s lemp recipe (only when
the project's stack is already up).
"""

from __future__ import annotations

import base64
import secrets
import shutil
import sys
from pathlib import Path

from shimkit.config import get_config
from shimkit.core import UI, CommandRunner, Event, Platform, emit_json, get_logger
from shimkit.core import version as _vc

_LOG = get_logger("framework.laravel")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69


class LaravelManager:
    def __init__(self) -> None:
        self._platform: Platform | None = None

    @classmethod
    def create(cls) -> LaravelManager:
        return cls()

    def boot(self) -> LaravelManager:
        self._platform = Platform.detect()
        if not (self._platform.is_macos or self._platform.is_linux):
            UI.error(
                "shimkit framework laravel targets macOS and Linux. "
                f"Detected platform: {self._platform.system}."
            )
            sys.exit(EX_UNAVAILABLE)
        return self

    # ─── perms ─────────────────────────────────────────────────────

    def perms(
        self,
        project: Path,
        *,
        web_group: str | None = None,
        dry_run: bool = False,
        json_out: bool = False,
    ) -> int:
        """Fix Laravel storage/bootstrap-cache permissions.

        Cross-distro group detection: uses the configured default
        (``www-data``) unless overridden. On macOS the dev account
        typically owns the project, so we only chmod and skip the
        group change unless `--group` is passed.
        """
        cfg = get_config().tools.framework.laravel
        assert self._platform is not None
        if not project.is_dir():
            UI.error(f"Not a directory: {project}")
            return EX_FAIL

        group = web_group or cfg.web_group
        writable = [project / d for d in cfg.writable_dirs]
        missing = [d for d in writable if not d.is_dir()]
        if missing:
            UI.warning(
                "These directories don't exist (Laravel app uninitialised?): "
                + ", ".join(str(m.relative_to(project)) for m in missing)
            )

        plan: list[list[str]] = []
        # 1. File / directory modes across the whole project tree (the
        #    source script ran chmod 664 + 775 globally; we keep that
        #    shape but skip system mount points).
        plan.append(
            ["find", str(project), "-type", "f", "-exec", "chmod", cfg.file_mode, "{}", "+"]
        )
        plan.append(
            ["find", str(project), "-type", "d", "-exec", "chmod", cfg.dir_mode, "{}", "+"]
        )
        # 2. Web group + ug+rwx on storage + bootstrap/cache only.
        for d in writable:
            if not d.exists():
                continue
            # chgrp only when the group exists on this host.
            if self._group_exists(group):
                plan.append(["chgrp", "-R", group, str(d)])
            else:
                UI.dim(f"  (group {group!r} not present; skipping chgrp on {d.relative_to(project)})")
            plan.append(["chmod", "-R", "ug+rwx", str(d)])

        if dry_run:
            UI.info("--dry-run: would run:")
            for cmd in plan:
                UI.line("  " + " ".join(cmd))
            return EX_OK

        failed: list[list[str]] = []
        for cmd in plan:
            r = CommandRunner.run(cmd)
            if not r.ok:
                failed.append(cmd)
                _LOG.warning("cmd failed: %s | stderr=%r", cmd, r.stderr)

        if json_out:
            emit_json(
                Event(
                    tool="framework.laravel",
                    step="perms",
                    status="warning" if failed else "ok",
                    data={
                        "project": str(project),
                        "group": group,
                        "writable_dirs": [str(d) for d in writable],
                        "failed": [" ".join(c) for c in failed],
                    },
                )
            )
            return EX_FAIL if failed else EX_OK

        if failed:
            UI.warning(f"{len(failed)} step(s) failed (see log).")
            return EX_FAIL
        UI.success(f"Laravel perms applied to {project} (group: {group}).")
        return EX_OK

    # ─── env ───────────────────────────────────────────────────────

    def env_scaffold(
        self,
        project: Path,
        *,
        app_name: str | None = None,
        app_env: str = "local",
        db_engine: str = "mysql",
        dry_run: bool = False,
    ) -> int:
        """Write a starter ``.env`` with a generated APP_KEY.

        Refuses to overwrite an existing ``.env`` (Laravel convention:
        the file is sensitive; we don't blow it away).
        """
        target = project / ".env"
        if target.exists():
            UI.error(f"{target} already exists; refusing to overwrite.")
            return EX_FAIL
        if not project.is_dir():
            UI.error(f"Not a directory: {project}")
            return EX_FAIL
        name = app_name or project.name
        app_key = "base64:" + base64.b64encode(secrets.token_bytes(32)).decode()
        body = _env_template(
            app_name=name,
            app_env=app_env,
            app_key=app_key,
            db_engine=db_engine,
        )
        if dry_run:
            UI.info(f"--dry-run: would write {len(body)} bytes to {target}.")
            return EX_OK
        try:
            target.write_text(body, encoding="utf-8")
        except OSError as exc:
            UI.error(f"Could not write {target}: {exc}")
            return EX_FAIL
        UI.success(f"Wrote {target} (APP_KEY generated).")
        return EX_OK

    # ─── cron-install ──────────────────────────────────────────────

    def cron_install(
        self,
        project: Path,
        *,
        name: str | None = None,
        schedule: str | None = None,
        dry_run: bool = False,
    ) -> int:
        """Install a `shimkit cron` entry that runs `php artisan schedule:run`."""
        if not project.is_dir():
            UI.error(f"Not a directory: {project}")
            return EX_FAIL
        artisan = project / "artisan"
        if not artisan.is_file():
            UI.error(f"No `artisan` binary at {artisan}; is this a Laravel project?")
            return EX_FAIL
        # Preflight php (the cron command itself needs `php` on PATH at
        # cron-fire time; failing here is friendlier than discovering it
        # at midnight).
        if shutil.which("php") is None:
            UI.warning(
                "`php` is not on PATH. The cron entry will be installed but "
                "won't run until php is available."
            )
        cfg = get_config().tools.framework.laravel
        entry_name = name or f"laravel-{project.name}"
        entry_schedule = schedule or cfg.default_cron_schedule
        cmd = f"cd {project} && php {artisan} schedule:run >> /dev/null 2>&1"

        from shimkit.tools.cron.manager import CronManager

        UI.info(f"Installing cron entry {entry_name!r}: {entry_schedule}  {cmd}")
        return (
            CronManager.create()
            .boot()
            .add(
                name=entry_name,
                schedule=entry_schedule,
                command=cmd,
                comment=f"Laravel scheduler for {project.name}",
                dry_run=dry_run,
            )
        )

    # ─── artisan ───────────────────────────────────────────────────

    def artisan(
        self,
        project: Path,
        args: list[str],
        *,
        in_container: bool = False,
        stack_project: str | None = None,
    ) -> int:
        """Run ``php artisan <args>``. Host by default; container with
        ``--in-container`` (uses ``shimkit stack lemp exec``)."""
        if not args:
            UI.error("No artisan arguments given.")
            return EX_FAIL
        if in_container:
            return self._artisan_in_container(args, stack_project=stack_project)
        return self._artisan_on_host(project, args)

    def _artisan_on_host(self, project: Path, args: list[str]) -> int:
        try:
            _vc.preflight(("php",))
        except _vc.VersionViolationError as exc:
            for violation in exc.results:
                if violation.status is _vc.Status.MISSING:
                    UI.error("`php` is not on PATH.")
                if violation.remediation:
                    UI.dim(f"  → {violation.remediation}")
            return EX_UNAVAILABLE
        if not (project / "artisan").is_file():
            UI.error(f"No `artisan` binary at {project / 'artisan'}.")
            return EX_FAIL
        cmd = ["php", "artisan", *args]
        result = CommandRunner.run(cmd, cwd=str(project), capture_output=False)
        return EX_OK if result.ok else EX_FAIL

    def _artisan_in_container(self, args: list[str], *, stack_project: str | None) -> int:
        from shimkit.tools.stack.manager import StackManager

        return (
            StackManager.create()
            .boot()
            .lemp()
            .exec_(cmd=["php", "artisan", *args], project=stack_project)
        )

    # ─── internals ─────────────────────────────────────────────────

    def _group_exists(self, group: str) -> bool:
        """Check whether `group` exists on the host. `getent` covers
        Linux; macOS has `dscl . -list /Groups` but `id -g <name>` /
        `getent group` are good cross-platform.
        """
        if shutil.which("getent"):
            r = CommandRunner.run(["getent", "group", group])
            return r.ok and bool(r.stdout.strip())
        # macOS fallback: try `dscl . -read /Groups/<name>`.
        if shutil.which("dscl"):
            r = CommandRunner.run(["dscl", ".", "-read", f"/Groups/{group}"])
            return r.ok
        # Last resort: ask the OS.
        try:
            import grp

            grp.getgrnam(group)
            return True
        except (ImportError, KeyError):
            return False


# ─── module helpers ──────────────────────────────────────────────────


def _env_template(
    *,
    app_name: str,
    app_env: str,
    app_key: str,
    db_engine: str,
) -> str:
    """Build a sensible starter `.env` for a Laravel app.

    Default db connection points at the shimkit-managed dev DB on
    127.0.0.1 (port 13306 for mysql/mariadb, 15432 for postgres) so a
    user who's already run `shimkit db <engine> up` gets a working
    connection on first `php artisan migrate`.
    """
    db_port_map = {"mysql": 13306, "mariadb": 13307, "postgres": 15432}
    db_port = db_port_map.get(db_engine, 13306)
    db_connection = "pgsql" if db_engine == "postgres" else "mysql"
    return (
        f"APP_NAME={app_name}\n"
        f"APP_ENV={app_env}\n"
        f"APP_KEY={app_key}\n"
        "APP_DEBUG=true\n"
        f"APP_URL=http://localhost\n"
        "\n"
        "LOG_CHANNEL=stack\n"
        "LOG_LEVEL=debug\n"
        "\n"
        f"DB_CONNECTION={db_connection}\n"
        f"DB_HOST=127.0.0.1\n"
        f"DB_PORT={db_port}\n"
        f"DB_DATABASE={app_name}\n"
        "DB_USERNAME=root\n"
        "DB_PASSWORD=shimkit-dev\n"
        "\n"
        "CACHE_DRIVER=file\n"
        "QUEUE_CONNECTION=sync\n"
        "SESSION_DRIVER=file\n"
        "\n"
        "MAIL_MAILER=log\n"
        "MAIL_FROM_ADDRESS=hello@example.com\n"
        f"MAIL_FROM_NAME=\"${{APP_NAME}}\"\n"
    )
