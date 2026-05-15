"""CronManager — orchestrator for ``shimkit cron``.

Owns the shell-outs to ``crontab -l`` (read) and ``crontab <file>``
(write). Pure parsing lives in :mod:`shimkit.tools.cron.parser`.

Backup-on-mutate: every write makes a timestamped copy of the
current crontab under ``tools.cron.backup_dir`` (default
``~/.shimkit/data/cron/``) so a bad ``add`` is recoverable via
``shimkit cron rollback``.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from shimkit.config import get_config
from shimkit.core import UI, CommandRunner, Event, Platform, emit_json, get_logger

from . import parser as _parser
from .models import CronEntry

_LOG = get_logger("cron")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69


class CronManager:
    def __init__(self) -> None:
        self._platform: Platform | None = None

    @classmethod
    def create(cls) -> CronManager:
        return cls()

    def boot(self) -> CronManager:
        self._platform = Platform.detect()
        if not (self._platform.is_macos or self._platform.is_linux):
            UI.error(
                f"shimkit cron targets macOS and Linux. Detected platform: {self._platform.system}."
            )
            sys.exit(EX_UNAVAILABLE)
        if shutil.which("crontab") is None:
            UI.error(
                "`crontab` is not on PATH. macOS: preinstalled. "
                "Linux: install `cron` (Debian/Ubuntu) or `cronie` (RHEL)."
            )
            sys.exit(EX_UNAVAILABLE)
        return self

    # ─── read ──────────────────────────────────────────────────────────

    def show(self, *, json_out: bool = False) -> int:
        body = self._read_crontab()
        if json_out:
            emit_json(
                Event(
                    tool="cron",
                    step="show",
                    status="ok",
                    data={"body": body, "lines": body.count("\n")},
                )
            )
            return EX_OK
        if not body.strip():
            UI.info("(empty crontab)")
            return EX_OK
        UI.header("user crontab")
        UI.line(body)
        return EX_OK

    def list_entries(self, *, json_out: bool = False) -> int:
        """List shimkit-managed entries (marker-tagged)."""
        cfg = get_config().tools.cron
        body = self._read_crontab()
        _, entries = _parser.parse(body, managed_prefix=cfg.managed_prefix)
        if json_out:
            emit_json(
                Event(
                    tool="cron",
                    step="list",
                    status="ok",
                    data={
                        "entries": [
                            {
                                "name": e.name,
                                "schedule": e.schedule,
                                "command": e.command,
                                "comment": e.comment,
                            }
                            for e in entries
                        ]
                    },
                )
            )
            return EX_OK
        if not entries:
            UI.info("No shimkit-managed cron entries.")
            return EX_OK
        UI.header(f"shimkit-managed cron entries ({len(entries)})")
        for e in entries:
            tail = f"  # {e.comment}" if e.comment else ""
            UI.line(f"  {e.name:20s} {e.schedule:14s} {e.command}{tail}")
        return EX_OK

    # ─── mutate ────────────────────────────────────────────────────────

    def add(
        self,
        *,
        name: str,
        schedule: str,
        command: str,
        comment: str | None = None,
        dry_run: bool = False,
    ) -> int:
        cfg = get_config().tools.cron
        if not _parser.is_valid_name(name):
            UI.error(f"Invalid name {name!r}: lowercase letter then alnum/_/- (1-64 chars).")
            return EX_FAIL
        if not _parser.is_valid_schedule(schedule):
            UI.error(
                f"Invalid schedule {schedule!r}: expected 5 fields or "
                "@reboot / @yearly / @monthly / @weekly / @daily / @hourly."
            )
            return EX_FAIL
        if not command.strip():
            UI.error("Empty command.")
            return EX_FAIL

        body = self._read_crontab()
        items, entries = _parser.parse(body, managed_prefix=cfg.managed_prefix)
        if any(e.name == name for e in entries):
            UI.error(
                f"An entry named {name!r} already exists. "
                "Use `shimkit cron remove` first, or pick a different name."
            )
            return EX_FAIL
        if len(entries) >= cfg.max_managed_entries:
            UI.error(
                f"Already at the configured cap of "
                f"{cfg.max_managed_entries} shimkit-managed entries."
            )
            return EX_FAIL

        # Append new entry to the end of the existing items list.
        items.append(CronEntry(name=name, schedule=schedule, command=command, comment=comment))
        new_body = _parser.render(items, managed_prefix=cfg.managed_prefix)
        return self._commit(new_body, dry_run=dry_run, action=f"add {name}")

    def remove(self, name: str, *, dry_run: bool = False) -> int:
        cfg = get_config().tools.cron
        body = self._read_crontab()
        items, entries = _parser.parse(body, managed_prefix=cfg.managed_prefix)
        if not any(e.name == name for e in entries):
            UI.info(f"No shimkit-managed entry named {name!r}; nothing to remove.")
            return EX_OK
        new_items: list[str | CronEntry] = [
            it for it in items if not (isinstance(it, CronEntry) and it.name == name)
        ]
        new_body = _parser.render(new_items, managed_prefix=cfg.managed_prefix)
        return self._commit(new_body, dry_run=dry_run, action=f"remove {name}")

    def rollback(self) -> int:
        """Restore the latest backup over the current crontab."""
        cfg = get_config().tools.cron
        backup_dir = Path(cfg.backup_dir).expanduser()
        if not backup_dir.is_dir():
            UI.error(f"No backup directory at {backup_dir}.")
            return EX_FAIL
        backups = sorted(backup_dir.glob("crontab-*.bak"))
        if not backups:
            UI.error("No backups to restore.")
            return EX_FAIL
        latest = backups[-1]
        UI.info(f"Restoring {latest}")
        if not self._write_crontab(latest.read_text(encoding="utf-8", errors="replace")):
            return EX_FAIL
        UI.success(f"Restored from {latest}.")
        return EX_OK

    # ─── internals ─────────────────────────────────────────────────────

    def _read_crontab(self) -> str:
        r = CommandRunner.run(["crontab", "-l"])
        # crontab returns 1 with "no crontab for ..." on stderr when
        # the user has no crontab yet. Treat that as an empty body.
        if not r.ok:
            return ""
        return r.stdout

    def _write_crontab(self, body: str) -> bool:
        fd, tmp = tempfile.mkstemp(prefix="shimkit-crontab-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
            r = CommandRunner.run(["crontab", tmp])
            if not r.ok:
                _LOG.warning("crontab load failed: %s", r.stderr.strip() or "?")
                UI.error(f"crontab refused the new file: {r.stderr.strip() or 'no detail'}")
                return False
            return True
        finally:
            Path(tmp).unlink(missing_ok=True)

    def _backup(self, body: str) -> Path | None:
        cfg = get_config().tools.cron
        backup_dir = Path(cfg.backup_dir).expanduser()
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _LOG.warning("Could not create %s: %s", backup_dir, exc)
            return None
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        path = backup_dir / f"crontab-{ts}.bak"
        try:
            path.write_text(body, encoding="utf-8")
        except OSError as exc:
            _LOG.warning("Backup write failed: %s", exc)
            return None
        return path

    def _commit(self, new_body: str, *, dry_run: bool, action: str) -> int:
        old = self._read_crontab()
        if dry_run:
            UI.info(f"--dry-run: would {action} (new crontab is {len(new_body)} bytes).")
            return EX_OK
        backup = self._backup(old)
        if backup is None:
            UI.warning("Continuing without a backup — could not write one.")
        if not self._write_crontab(new_body):
            return EX_FAIL
        UI.success(f"{action} ✓")
        if backup is not None:
            UI.dim(f"  backup: {backup}")
        return EX_OK
