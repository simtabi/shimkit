"""HostsManager — orchestrator for ``shimkit hosts``.

Reads + mutates the hosts file (default ``/etc/hosts``) with the same
atomic-write + timestamped-backup pattern as
``adguard.resolv.write_resolv_static``. Subprocess shell-outs (sudo
install, sudo cp) go through CommandRunner; pure parser logic lives
in :mod:`shimkit.tools.hosts.editor`.

The hosts path is injectable via ``boot(hosts_path_override=...)`` so
tests can target a tempdir without monkeypatching globals.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from shimkit.config import get_config
from shimkit.core import (
    UI,
    CommandRunner,
    Event,
    Menu,
    Platform,
    emit_json,
    get_logger,
    is_root,
    sudo_prefix,
)

from . import editor as _editor
from .editor import HostsFile

_LOG = get_logger("hosts")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69
EX_NOPERM = 77


class HostsManager:
    def __init__(self) -> None:
        self._platform: Platform | None = None
        self._hosts_path: Path | None = None

    @classmethod
    def create(cls) -> HostsManager:
        return cls()

    def boot(self, *, hosts_path_override: Path | None = None) -> HostsManager:
        self._platform = Platform.detect()
        if not (self._platform.is_macos or self._platform.is_linux):
            UI.error(
                "shimkit hosts targets macOS and Linux. "
                f"Detected platform: {self._platform.system}."
            )
            sys.exit(EX_UNAVAILABLE)
        cfg = get_config().tools.hosts
        path = hosts_path_override or Path(cfg.hosts_path)
        if not path.exists():
            UI.error(f"Hosts file not found at {path}.")
            sys.exit(EX_UNAVAILABLE)
        self._hosts_path = path
        return self

    # ---- read-only ------------------------------------------------------

    def show(self, *, json_out: bool = False) -> int:
        hf = self._read()
        entries = hf.entries()
        if json_out:
            emit_json(
                Event(
                    tool="hosts",
                    step="show",
                    status="ok",
                    data={
                        "path": str(self._hosts_path),
                        "entries": [
                            {"ip": e.ip, "name": e.name, "comment": e.comment} for e in entries
                        ],
                    },
                )
            )
            return EX_OK
        if not entries:
            UI.info("No entries in hosts file.")
            return EX_OK
        UI.header(f"hosts ({len(entries)} entries) — {self._hosts_path}")
        for e in entries:
            tag = f"  # {e.comment}" if e.comment else ""
            UI.line(f"  {e.ip}\t{e.name}{tag}")
        return EX_OK

    # ---- mutators -------------------------------------------------------

    def add(self, ip: str, name: str, *, dry_run: bool = False) -> int:
        if not _editor.is_valid_ip(ip):
            UI.error(f"Not a valid IP: {ip!r}")
            return EX_FAIL
        hf = self._read()
        if not hf.add(ip, name, comment="shimkit-managed"):
            UI.info(f"{ip}\t{name} already present; nothing to do.")
            return EX_OK
        return self._commit(hf, dry_run=dry_run, action=f"add {ip} {name}")

    def remove(self, name: str, *, dry_run: bool = False) -> int:
        hf = self._read()
        removed = hf.remove(name)
        if removed == 0:
            UI.info(f"{name} not present; nothing to remove.")
            return EX_OK
        return self._commit(hf, dry_run=dry_run, action=f"remove {name} ({removed} entries)")

    def block(self, domain: str, *, dry_run: bool = False) -> int:
        """Convenience: add `127.0.0.1 <domain>`. Idempotent."""
        return self.add("127.0.0.1", domain, dry_run=dry_run)

    def unblock(self, domain: str, *, dry_run: bool = False) -> int:
        """Convenience for remove(domain). Idempotent."""
        return self.remove(domain, dry_run=dry_run)

    def apply_list(
        self,
        source: str,
        *,
        dry_run: bool = False,
    ) -> int:
        """Apply a StevenBlack-style list from a URL or local path.

        Caller is responsible for the SEVERE token check; this method
        assumes authorisation has already been granted.
        """
        text = self._read_source(source)
        if text is None:
            return EX_FAIL
        pairs = _editor.parse_block_list(text)
        cfg = get_config().tools.hosts
        if len(pairs) > cfg.max_entries_per_apply:
            UI.error(
                f"List contains {len(pairs)} entries; cap is "
                f"{cfg.max_entries_per_apply}. Either narrow the list or "
                f"raise `tools.hosts.max_entries_per_apply` in your config."
            )
            return EX_FAIL
        hf = self._read()
        added = 0
        for ip, name in pairs:
            if hf.add(ip, name, comment="shimkit-managed"):
                added += 1
        if added == 0:
            UI.info("List applied; no new entries (all already present).")
            return EX_OK
        return self._commit(hf, dry_run=dry_run, action=f"apply-list ({added} new entries)")

    def rollback(self) -> int:
        """Restore the latest ``<hosts_path>.bak-*`` over the live file."""
        assert self._hosts_path is not None
        parent = self._hosts_path.parent
        stem = self._hosts_path.name
        backups = sorted(parent.glob(f"{stem}.bak-*"))
        if not backups:
            UI.error("No backup found.")
            return EX_FAIL
        latest = backups[-1]
        UI.info(f"Restoring {latest} → {self._hosts_path}")
        if not self._sudo_install(latest, self._hosts_path):
            UI.error("Restore failed. Check `sudo` access and try again.")
            return EX_FAIL
        UI.success(f"Restored from {latest}.")
        return EX_OK

    # ---- interactive ---------------------------------------------------

    def run(self) -> None:
        while True:
            picked = Menu.select(
                "shimkit hosts",
                ["List entries", "Rollback to last backup", "Quit"],
            )
            if picked is None or picked == "Quit":
                return
            if picked == "List entries":
                self.show()
            elif picked == "Rollback to last backup" and Menu.confirm(
                "Restore the most recent backup?", default=False
            ):
                self.rollback()

    # ---- internal -------------------------------------------------------

    def _read(self) -> HostsFile:
        assert self._hosts_path is not None
        try:
            text = self._hosts_path.read_text(encoding="utf-8")
        except OSError as exc:
            UI.error(f"Could not read {self._hosts_path}: {exc}")
            sys.exit(EX_FAIL)
        return HostsFile.parse(text)

    def _read_source(self, source: str) -> str | None:
        """URL → download; local path → read; anything else → error."""
        if source.startswith(("http://", "https://")):
            import urllib.error
            import urllib.request

            # Scheme is gated to http/https on the previous line — no
            # file:// or custom-scheme bandit footgun. # nosec B310.
            req = urllib.request.Request(  # nosec B310
                source, headers={"User-Agent": "shimkit/hosts"}
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310
                    body: bytes = r.read()
                return body.decode("utf-8", errors="replace")
            except (urllib.error.URLError, TimeoutError) as exc:
                UI.error(f"Could not fetch {source}: {exc}")
                return None
        p = Path(source).expanduser()
        if not p.is_file():
            UI.error(f"List source not found: {source}")
            return None
        try:
            return p.read_text(encoding="utf-8")
        except OSError as exc:
            UI.error(f"Could not read {p}: {exc}")
            return None

    def _commit(self, hf: HostsFile, *, dry_run: bool, action: str) -> int:
        assert self._hosts_path is not None
        rendered = hf.render()
        if dry_run:
            UI.info(f"--dry-run: would {action} ({len(rendered)} bytes).")
            return EX_OK
        bak = self._back_up()
        if bak is None:
            UI.warning("Continuing without a backup — could not write one.")
        if not self._atomic_write(rendered):
            UI.error("Write failed. See above for the underlying error.")
            return EX_FAIL
        UI.success(f"{action} → {self._hosts_path}")
        if bak:
            UI.dim(f"backup: {bak}")
        return EX_OK

    def _back_up(self) -> Path | None:
        assert self._hosts_path is not None
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        bak = self._hosts_path.with_name(f"{self._hosts_path.name}.bak-{ts}")
        r = CommandRunner.run(
            [*sudo_prefix(), "cp", "-a", str(self._hosts_path), str(bak)],
            capture_output=True,
        )
        if not r.ok:
            _LOG.warning("Backup to %s failed: %s", bak, r.stderr)
            return None
        return bak

    def _atomic_write(self, content: str) -> bool:
        """Write ``content`` to the hosts path atomically.

        Mirror of ``adguard.resolv.write_resolv_static``: try
        ``sudo install`` (atomic replace via the inode), fall back to a
        direct write through the existing inode if we're root.
        """
        assert self._hosts_path is not None
        fd, tmp = tempfile.mkstemp(prefix="shimkit-hosts-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            if self._sudo_install(Path(tmp), self._hosts_path):
                return True
            # Fall back for cases where the hosts file is a bind-mount
            # (typical inside containers) and `install` can't replace
            # the inode. Requires we already have root.
            if is_root():
                try:
                    self._hosts_path.write_text(content, encoding="utf-8")
                    return True
                except OSError as exc:
                    _LOG.warning("Direct write to %s failed: %s", self._hosts_path, exc)
            return False
        finally:
            Path(tmp).unlink(missing_ok=True)

    def _sudo_install(self, src: Path, dst: Path) -> bool:
        r = CommandRunner.run(
            [
                *sudo_prefix(),
                "install",
                "-m",
                "0644",
                "-o",
                "root",
                str(src),
                str(dst),
            ],
            capture_output=True,
        )
        if not r.ok:
            _LOG.warning("install %s → %s failed: %s", src, dst, r.stderr.strip())
        return r.ok
