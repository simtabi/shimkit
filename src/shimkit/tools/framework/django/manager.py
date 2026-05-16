"""DjangoManager -- orchestrator for ``shimkit framework django``.

Mirrors the Laravel + Symfony recipes. Divergences:

- Console binary is ``manage.py`` at the project root (no shipping
  binary at `bin/console` or `artisan`).
- Python entrypoint is ``python`` not ``php``, so ``console``
  preflights ``python`` rather than ``php``.
- ``SECRET_KEY`` is the Django convention (not ``APP_KEY`` /
  ``APP_SECRET``). 50 chars of URL-safe random.
- ``DATABASE_URL`` is the django-environ / dj-database-url
  convention; we emit it expecting the user has one of those
  packages installed.
"""

from __future__ import annotations

import secrets
import shutil
import string
import sys
from pathlib import Path

from shimkit.config import get_config
from shimkit.core import UI, CommandRunner, Event, Platform, emit_json, get_logger
from shimkit.core import version as _vc

_LOG = get_logger("framework.django")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69


class DjangoManager:
    def __init__(self) -> None:
        self._platform: Platform | None = None

    @classmethod
    def create(cls) -> DjangoManager:
        return cls()

    def boot(self) -> DjangoManager:
        self._platform = Platform.detect()
        if not (self._platform.is_macos or self._platform.is_linux):
            UI.error(
                "shimkit framework django targets macOS and Linux. "
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
        """Fix Django media/ + staticfiles/ permissions.

        `staticfiles/` is the collectstatic output dir; may not exist
        on a fresh project, in which case it's skipped with a warning
        (same shape as the Laravel / Symfony recipes).
        """
        cfg = get_config().tools.framework.django
        assert self._platform is not None
        if not project.is_dir():
            UI.error(f"Not a directory: {project}")
            return EX_FAIL

        group = web_group or cfg.web_group
        writable = [project / d for d in cfg.writable_dirs]
        missing = [d for d in writable if not d.is_dir()]
        if missing:
            UI.warning(
                "These directories don't exist (haven't run "
                "`collectstatic` / no uploads yet?): "
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
                    f"  (group {group!r} not present; skipping chgrp on "
                    f"{d.relative_to(project)})"
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
                    tool="framework.django",
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
        UI.success(f"Django perms applied to {project} (group: {group}).")
        return EX_OK

    # ─── env ───────────────────────────────────────────────────────

    def env_scaffold(
        self,
        project: Path,
        *,
        app_name: str | None = None,
        debug: bool | None = None,
        db_engine: str = "postgres",
        dry_run: bool = False,
    ) -> int:
        """Write a starter ``.env`` with a generated SECRET_KEY +
        DATABASE_URL. Refuses to overwrite an existing ``.env``.

        Default DB engine is **postgres** (Django's most common
        pairing — sqlite is the framework default but not what most
        teams ship). Override with ``--db mysql`` or ``--db mariadb``.
        """
        target = project / ".env"
        if target.exists():
            UI.error(f"{target} already exists; refusing to overwrite.")
            return EX_FAIL
        if not project.is_dir():
            UI.error(f"Not a directory: {project}")
            return EX_FAIL
        cfg = get_config().tools.framework.django
        name = app_name or project.name
        resolved_debug = cfg.default_debug if debug is None else debug
        secret_key = _generate_secret_key()
        body = _env_template(
            app_name=name,
            debug=resolved_debug,
            secret_key=secret_key,
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
        UI.success(f"Wrote {target} (SECRET_KEY generated).")
        return EX_OK

    # ─── migrate ───────────────────────────────────────────────────

    def migrate(
        self,
        project: Path,
        *,
        in_container: bool = False,
        stack_project: str | None = None,
    ) -> int:
        """Run ``python manage.py migrate``."""
        return self.manage(
            project,
            ["migrate", "--no-input"],
            in_container=in_container,
            stack_project=stack_project,
        )

    # ─── manage ────────────────────────────────────────────────────

    def manage(
        self,
        project: Path,
        args: list[str],
        *,
        in_container: bool = False,
        stack_project: str | None = None,
    ) -> int:
        """Run ``python manage.py <args>``. Host by default; in-container
        via ``shimkit stack lemp``."""
        if not args:
            UI.error("No manage.py arguments given.")
            return EX_FAIL
        if in_container:
            return self._manage_in_container(args, stack_project=stack_project)
        return self._manage_on_host(project, args)

    def _manage_on_host(self, project: Path, args: list[str]) -> int:
        try:
            _vc.preflight(("python",))
        except _vc.VersionViolationError as exc:
            for violation in exc.results:
                if violation.status is _vc.Status.MISSING:
                    UI.error("`python` is not on PATH.")
                if violation.remediation:
                    UI.dim(f"  → {violation.remediation}")
            return EX_UNAVAILABLE
        manage_py = project / "manage.py"
        if not manage_py.is_file():
            UI.error(f"No `manage.py` at {manage_py}. Is this a Django project?")
            return EX_FAIL
        cmd = [sys.executable, str(manage_py), *args]
        result = CommandRunner.run(cmd, cwd=str(project), capture_output=False)
        return EX_OK if result.ok else EX_FAIL

    def _manage_in_container(self, args: list[str], *, stack_project: str | None) -> int:
        from shimkit.tools.stack.manager import StackManager

        return (
            StackManager.create()
            .boot()
            .lemp()
            .exec_(cmd=["python", "manage.py", *args], project=stack_project)
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


def _generate_secret_key(length: int = 50) -> str:
    """Reproduce Django's ``get_random_secret_key()`` shape without
    importing Django (we don't depend on it).

    Django uses 50 chars from the alphabet [a-zA-Z0-9!@#$%^&*(-_=+)].
    We use the same alphabet for compatibility.
    """
    alphabet = (
        string.ascii_lowercase + string.ascii_uppercase + string.digits + "!@#$%^&*(-_=+)"
    )
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _env_template(
    *,
    app_name: str,
    debug: bool,
    secret_key: str,
    db_engine: str,
) -> str:
    """Build a starter `.env` for a Django project.

    Format is django-environ / python-decouple compatible:
    `KEY=value` lines. `DATABASE_URL` follows the Heroku /
    dj-database-url convention.
    """
    db_port_map = {"mysql": 13306, "mariadb": 13307, "postgres": 15432}
    db_port = db_port_map.get(db_engine, 15432)
    db_proto = "postgres" if db_engine == "postgres" else "mysql"
    db_url = f"{db_proto}://root:shimkit-dev@127.0.0.1:{db_port}/{app_name}"
    return (
        f"# Django local environment overrides.\n"
        f"# Read by django-environ / python-decouple from .env at\n"
        f"# project root. Production should override via real secrets\n"
        f"# management.\n"
        f"\n"
        f"SECRET_KEY={secret_key}\n"
        f"DEBUG={'True' if debug else 'False'}\n"
        f'ALLOWED_HOSTS="localhost,127.0.0.1"\n'
        f"\n"
        f'DATABASE_URL="{db_url}"\n'
        f"\n"
        f"# Cache + queue (pair with `shimkit db redis up`).\n"
        f'# REDIS_URL="redis://default:shimkit-dev@127.0.0.1:16379/0"\n'
        f"\n"
        f"# Email — defaults to the console backend; override in prod.\n"
        f"EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend\n"
    )
