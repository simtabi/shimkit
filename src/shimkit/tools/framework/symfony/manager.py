"""SymfonyManager -- orchestrator for ``shimkit framework symfony``.

Pure-host operations (perms, env scaffold) shell out via
``CommandRunner``. ``cache-clear`` and ``console`` run on the host
by default; ``--in-container`` routes through
:class:`shimkit.tools.stack.StackManager`'s lemp recipe.

Modelled on :class:`shimkit.tools.framework.laravel.LaravelManager`.
The two managers diverge on:

- writable dirs (``var`` vs ``storage`` + ``bootstrap/cache``)
- env-file shape (``APP_SECRET`` hex vs ``APP_KEY`` base64)
- console entrypoint (``bin/console`` vs ``artisan``)
- no scheduler / cron-install (Symfony has no built-in scheduler)
"""

from __future__ import annotations

import secrets
import shutil
import sys
from pathlib import Path

from shimkit.config import get_config
from shimkit.core import UI, CommandRunner, Event, Platform, emit_json, get_logger
from shimkit.core import version as _vc

_LOG = get_logger("framework.symfony")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69


class SymfonyManager:
    def __init__(self) -> None:
        self._platform: Platform | None = None

    @classmethod
    def create(cls) -> SymfonyManager:
        return cls()

    def boot(self) -> SymfonyManager:
        self._platform = Platform.detect()
        if not (self._platform.is_macos or self._platform.is_linux):
            UI.error(
                "shimkit framework symfony targets macOS and Linux. "
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
        """Fix Symfony var/ permissions.

        Cross-distro group detection mirrors the Laravel manager.
        Symfony's writable tree is just ``var/`` by default (covers
        cache/, log/, sessions/). Extending to ``public/uploads/``
        etc. is per-project — set ``tools.framework.symfony.writable_dirs``
        in your user config.
        """
        cfg = get_config().tools.framework.symfony
        assert self._platform is not None
        if not project.is_dir():
            UI.error(f"Not a directory: {project}")
            return EX_FAIL

        group = web_group or cfg.web_group
        writable = [project / d for d in cfg.writable_dirs]
        missing = [d for d in writable if not d.is_dir()]
        if missing:
            UI.warning(
                "These directories don't exist (Symfony app uninitialised?): "
                + ", ".join(str(m.relative_to(project)) for m in missing)
            )

        plan: list[list[str]] = []
        plan.append(
            ["find", str(project), "-type", "f", "-exec", "chmod", cfg.file_mode, "{}", "+"]
        )
        plan.append(
            ["find", str(project), "-type", "d", "-exec", "chmod", cfg.dir_mode, "{}", "+"]
        )
        for d in writable:
            if not d.exists():
                continue
            if self._group_exists(group):
                plan.append(["chgrp", "-R", group, str(d)])
            else:
                UI.dim(
                    f"  (group {group!r} not present; skipping chgrp on {d.relative_to(project)})"
                )
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
                    tool="framework.symfony",
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
        UI.success(f"Symfony perms applied to {project} (group: {group}).")
        return EX_OK

    # ─── env ───────────────────────────────────────────────────────

    def env_scaffold(
        self,
        project: Path,
        *,
        app_name: str | None = None,
        app_env: str | None = None,
        db_engine: str = "mysql",
        dry_run: bool = False,
    ) -> int:
        """Write a starter ``.env.local`` with a generated APP_SECRET.

        Symfony's convention is ``.env`` (checked in, framework
        defaults) + ``.env.local`` (gitignored, your secrets). We
        write to ``.env.local`` so the framework-provided ``.env``
        is preserved. Refuses to overwrite an existing
        ``.env.local`` for the same secrecy reason Laravel's env
        scaffold refuses ``.env``.
        """
        target = project / ".env.local"
        if target.exists():
            UI.error(f"{target} already exists; refusing to overwrite.")
            return EX_FAIL
        if not project.is_dir():
            UI.error(f"Not a directory: {project}")
            return EX_FAIL
        cfg = get_config().tools.framework.symfony
        name = app_name or project.name
        resolved_env = app_env or cfg.default_env
        # Symfony APP_SECRET: 32 random bytes encoded as hex.
        # https://symfony.com/doc/current/reference/configuration/framework.html#secret
        app_secret = secrets.token_hex(32)
        body = _env_template(
            app_name=name,
            app_env=resolved_env,
            app_secret=app_secret,
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
        UI.success(f"Wrote {target} (APP_SECRET generated).")
        return EX_OK

    # ─── cache-clear ───────────────────────────────────────────────

    def cache_clear(
        self,
        project: Path,
        *,
        app_env: str | None = None,
        in_container: bool = False,
        stack_project: str | None = None,
    ) -> int:
        """Run ``php bin/console cache:clear`` for the project."""
        cfg = get_config().tools.framework.symfony
        resolved_env = app_env or cfg.default_env
        args = ["cache:clear", f"--env={resolved_env}"]
        return self.console(
            project,
            args,
            in_container=in_container,
            stack_project=stack_project,
        )

    # ─── console ───────────────────────────────────────────────────

    def console(
        self,
        project: Path,
        args: list[str],
        *,
        in_container: bool = False,
        stack_project: str | None = None,
    ) -> int:
        """Run ``php bin/console <args>``. Host by default."""
        if not args:
            UI.error("No bin/console arguments given.")
            return EX_FAIL
        if in_container:
            return self._console_in_container(args, stack_project=stack_project)
        return self._console_on_host(project, args)

    def _console_on_host(self, project: Path, args: list[str]) -> int:
        try:
            _vc.preflight(("php",))
        except _vc.VersionViolationError as exc:
            for violation in exc.results:
                if violation.status is _vc.Status.MISSING:
                    UI.error("`php` is not on PATH.")
                if violation.remediation:
                    UI.dim(f"  → {violation.remediation}")
            return EX_UNAVAILABLE
        console_bin = project / "bin" / "console"
        if not console_bin.is_file():
            UI.error(
                f"No `bin/console` at {console_bin}. Is this a Symfony project?"
            )
            return EX_FAIL
        cmd = ["php", str(console_bin), *args]
        result = CommandRunner.run(cmd, cwd=str(project), capture_output=False)
        return EX_OK if result.ok else EX_FAIL

    def _console_in_container(self, args: list[str], *, stack_project: str | None) -> int:
        from shimkit.tools.stack.manager import StackManager

        return (
            StackManager.create()
            .boot()
            .lemp()
            .exec_(cmd=["php", "bin/console", *args], project=stack_project)
        )

    # ─── internals ─────────────────────────────────────────────────

    def _group_exists(self, group: str) -> bool:
        if shutil.which("getent"):
            r = CommandRunner.run(["getent", "group", group])
            return r.ok and bool(r.stdout.strip())
        if shutil.which("dscl"):
            r = CommandRunner.run(["dscl", ".", "-read", f"/Groups/{group}"])
            return r.ok
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
    app_secret: str,
    db_engine: str,
) -> str:
    """Build a sensible starter `.env.local` for a Symfony app.

    DB URL points at shimkit-managed dev DBs (`shimkit db` ports)
    so a user who's already run `shimkit db <engine> up` gets a
    working DATABASE_URL on first `bin/console doctrine:migrations:migrate`.
    """
    db_port_map = {"mysql": 13306, "mariadb": 13307, "postgres": 15432}
    db_port = db_port_map.get(db_engine, 13306)
    db_proto = "postgresql" if db_engine == "postgres" else "mysql"
    db_version = {
        "mysql": "?serverVersion=8.0",
        "mariadb": "?serverVersion=mariadb-10.11",
        "postgres": "?serverVersion=16",
    }.get(db_engine, "")
    db_url = (
        f"{db_proto}://root:shimkit-dev@127.0.0.1:{db_port}/{app_name}{db_version}"
    )
    return (
        f"# Symfony local environment overrides (gitignored).\n"
        f"# Framework defaults live in .env; secrets and per-host\n"
        f"# tweaks belong here.\n"
        f"\n"
        f"APP_ENV={app_env}\n"
        f"APP_SECRET={app_secret}\n"
        f"\n"
        f"DATABASE_URL=\"{db_url}\"\n"
        f"\n"
        f"# Mailer — defaults to in-memory; override in prod.\n"
        f"MAILER_DSN=null://null\n"
    )
