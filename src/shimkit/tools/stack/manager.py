"""StackManager — orchestrator for ``shimkit stack``.

Thin shell over the per-recipe modules. Today there's one recipe
(``lemp``); future ``mern`` / ``rails`` / ``mean`` slot in by
adding another module + registering it in ``RECIPES``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from shimkit.config import get_config
from shimkit.core import UI, DockerEnv, Event, emit_json, get_logger
from shimkit.core import version as _vc

from . import lemp as _lemp

_LOG = get_logger("stack")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69

SCOPE = "stack"


class StackManager:
    """Multi-container app orchestration. Composes the W3 db engine
    registry with an nginx + php-fpm pair per recipe.
    """

    def __init__(self) -> None:
        self._env: DockerEnv | None = None

    @classmethod
    def create(cls) -> StackManager:
        return cls()

    def boot(self, *, force: bool = False) -> StackManager:
        try:
            _vc.preflight(("docker",), force=force)
        except _vc.VersionViolationError as exc:
            for r in exc.results:
                if r.status is _vc.Status.MISSING:
                    UI.error("`docker` is not on PATH.")
                elif r.status is _vc.Status.OUT_OF_RANGE and r.tool_version:
                    UI.error(
                        f"docker {r.tool_version.raw} is out of range — "
                        f"shimkit stack requires {r.constraint.min or '<any>'}+."
                    )
                if r.remediation:
                    UI.dim(f"  → {r.remediation}")
            sys.exit(EX_UNAVAILABLE)
        self._env = DockerEnv.create().boot()
        return self

    # ── ls ───────────────────────────────────────────────────────────

    def ls(self, *, json_out: bool = False) -> int:
        assert self._env is not None
        containers = self._env.list_managed(scope=SCOPE)
        # Group by project (label `shimkit.project`).
        projects: dict[str, dict[str, str]] = {}
        for c in containers:
            labels = getattr(c, "labels", {}) or {}
            project = labels.get("shimkit.project", "?")
            role = labels.get("shimkit.role", "?")
            projects.setdefault(project, {})[role] = str(getattr(c, "status", "?") or "?")
        if json_out:
            emit_json(
                Event(
                    tool="stack",
                    step="ls",
                    status="ok",
                    data={
                        "projects": [
                            {"project": p, "roles": roles} for p, roles in sorted(projects.items())
                        ]
                    },
                )
            )
            return EX_OK
        if not projects:
            UI.info("No shimkit-managed stacks.")
            return EX_OK
        UI.header(f"shimkit stack ({len(projects)} project(s))")
        for p, roles in sorted(projects.items()):
            roles_str = ", ".join(f"{r}={s}" for r, s in sorted(roles.items()))
            UI.line(f"  {p}: {roles_str}")
        return EX_OK

    # ── recipe accessors ─────────────────────────────────────────────

    def lemp(self) -> _LempBound:
        assert self._env is not None
        return _LempBound(env=self._env)


class _LempBound:
    def __init__(self, *, env: DockerEnv) -> None:
        self._env = env

    def up(
        self,
        *,
        project: str | None = None,
        db_engine: str | None = None,
        host_port: int | None = None,
        project_root: Path | None = None,
        password: str | None = None,
        json_out: bool = False,
        dry_run: bool = False,
    ) -> int:
        scfg = get_config().tools.stack
        dcfg = get_config().tools.db
        proj = project or scfg.default_project
        db_eng = db_engine or scfg.lemp.default_db
        port = host_port or scfg.lemp.default_port
        root = (project_root or Path.cwd()).expanduser().resolve()
        pwd = password or dcfg.default_password

        if db_eng not in dcfg.engines:
            UI.error(f"Unknown db engine {db_eng!r}. Known: {', '.join(dcfg.engines)}.")
            return EX_FAIL

        try:
            actions = _lemp.up(
                self._env,
                project=proj,
                db_engine=db_eng,
                host_port=port,
                project_root=root,
                db_password=pwd,
                dry_run=dry_run,
            )
        except ValueError as exc:
            UI.error(str(exc))
            return EX_FAIL

        if json_out:
            emit_json(
                Event(
                    tool="stack",
                    step="lemp.up",
                    status="ok",
                    data={
                        "project": proj,
                        "db_engine": db_eng,
                        "host_port": port,
                        "project_root": str(root),
                        "actions": actions,
                    },
                )
            )
            return EX_OK
        if dry_run:
            UI.info(f"--dry-run: would create LEMP stack for project {proj!r}.")
            for role, action in actions.items():
                UI.line(f"  {role}: {action}")
            return EX_OK
        UI.success(f"LEMP stack {proj!r} is up.")
        UI.line(f"  → http://127.0.0.1:{port}")
        for role, action in actions.items():
            UI.dim(f"  {role:7s} {action}")
        return EX_OK

    def down(
        self,
        *,
        project: str | None = None,
        json_out: bool = False,
        dry_run: bool = False,
    ) -> int:
        proj = project or get_config().tools.stack.default_project
        if dry_run:
            UI.info(f"--dry-run: would stop + remove LEMP stack for {proj!r}.")
            return EX_OK
        actions = _lemp.down(self._env, project=proj)
        if json_out:
            emit_json(
                Event(
                    tool="stack",
                    step="lemp.down",
                    status="ok",
                    data={"project": proj, "actions": actions},
                )
            )
            return EX_OK
        UI.success(f"LEMP stack {proj!r} torn down.")
        for role, action in actions.items():
            UI.dim(f"  {role:7s} {action}")
        return EX_OK

    def status(self, *, project: str | None = None, json_out: bool = False) -> int:
        proj = project or get_config().tools.stack.default_project
        state = _lemp.status(self._env, project=proj)
        if json_out:
            emit_json(
                Event(
                    tool="stack",
                    step="lemp.status",
                    status="ok" if state.all_running() else "warning",
                    data={
                        "project": state.project,
                        "network": state.network,
                        "db": state.db,
                        "php": state.php,
                        "nginx": state.nginx,
                        "db_engine": state.db_engine,
                        "host_port": state.host_port,
                        "all_running": state.all_running(),
                    },
                )
            )
            return EX_OK
        UI.header(f"LEMP stack — {state.project}")
        UI.line(f"  db    {state.db}")
        UI.line(f"  php   {state.php}")
        UI.line(f"  nginx {state.nginx}")
        UI.dim(f"  network: {state.network}")
        if state.all_running():
            UI.dim(f"  → http://127.0.0.1:{state.host_port}")
        return EX_OK

    def logs(
        self,
        *,
        project: str | None = None,
        follow: bool = False,
        tail: int = 100,
    ) -> int:
        proj = project or get_config().tools.stack.default_project
        for role in ("nginx", "php", "db"):
            name = _lemp._container_name(proj, role)
            blob = self._env.logs(name, follow=False, tail=tail)
            if blob is None:
                continue
            UI.header(f"{role} — {name}")
            text = (
                blob.decode("utf-8", errors="replace")
                if isinstance(blob, bytes | bytearray)
                else str(blob)
            )
            UI.line(text)
        if follow:
            UI.dim(
                "(follow not implemented for the multi-container case; use `docker logs -f <name>`.)"
            )
        return EX_OK

    def exec_(
        self,
        *,
        cmd: list[str],
        project: str | None = None,
    ) -> int:
        proj = project or get_config().tools.stack.default_project
        if not cmd:
            UI.error("No command given.")
            return EX_FAIL
        exit_code, stdout, stderr = _lemp.exec_in_php(self._env, project=proj, cmd=cmd)
        if stdout:
            UI.line(stdout)
        if stderr:
            UI.line(stderr)
        return EX_OK if exit_code == 0 else EX_FAIL
