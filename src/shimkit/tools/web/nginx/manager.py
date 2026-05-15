"""WebNginxManager — orchestrator for ``shimkit web nginx``.

Three modes:

- ``generate`` — render a vhost file. Default writes to stdout (or
  to ``--out PATH`` if given). NO host mutation. Idempotent.
- ``apply`` — SEVERE. Write to ``sites-available``, symlink into
  ``sites-enabled``, ``nginx -s reload``. Requires the configured
  severe-tier token. Refuses to overwrite a non-shimkit-managed
  vhost (the file is identified by its managed marker comment).
- ``remove`` — SEVERE. Reverse of apply. Also refuses to remove a
  vhost without the managed marker.
- ``list`` — read ``sites-enabled`` and report which vhosts shimkit
  manages.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from shimkit.config import get_config
from shimkit.core import (
    UI,
    CommandRunner,
    Event,
    Platform,
    emit_json,
    get_logger,
    is_root,
    sudo_prefix,
)

from . import templates

_LOG = get_logger("web.nginx")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69
EX_NOPERM = 77


class WebNginxManager:
    """Builder: ``WebNginxManager.create().boot().<op>(...)``."""

    def __init__(self) -> None:
        self._platform: Platform | None = None

    @classmethod
    def create(cls) -> WebNginxManager:
        return cls()

    def boot(self) -> WebNginxManager:
        self._platform = Platform.detect()
        # generate is always host-platform-agnostic. apply/remove need
        # nginx-on-host; those check at invocation time, not boot.
        if not (self._platform.is_macos or self._platform.is_linux):
            UI.error(
                f"shimkit web nginx targets macOS and Linux. "
                f"Detected platform: {self._platform.system}."
            )
            sys.exit(EX_UNAVAILABLE)
        return self

    # ─── generate ───────────────────────────────────────────────────

    def generate(
        self,
        *,
        name: str,
        domain: str,
        root: str,
        flavor: str | None = None,
        php_version: str | None = None,
        out: Path | None = None,
        json_out: bool = False,
    ) -> int:
        cfg = get_config().tools.web.nginx
        flav = flavor or cfg.default_flavor
        php = php_version or cfg.default_php_version
        try:
            body = templates.render(
                flav,
                name=name,
                domain=domain,
                root=root,
                php_version=php,
                managed_marker=cfg.managed_marker,
            )
        except ValueError as exc:
            UI.error(str(exc))
            return EX_FAIL

        if out is None:
            if json_out:
                emit_json(
                    Event(
                        tool="web.nginx",
                        step="vhost.generate",
                        status="ok",
                        data={
                            "name": name,
                            "domain": domain,
                            "root": root,
                            "flavor": flav,
                            "php_version": php,
                            "body": body,
                        },
                    )
                )
                return EX_OK
            UI.line(body)
            return EX_OK

        out = out.expanduser()
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(body, encoding="utf-8")
        except OSError as exc:
            UI.error(f"Could not write {out}: {exc}")
            return EX_FAIL
        if json_out:
            emit_json(
                Event(
                    tool="web.nginx",
                    step="vhost.generate",
                    status="ok",
                    data={
                        "name": name,
                        "domain": domain,
                        "flavor": flav,
                        "out": str(out),
                        "bytes": len(body),
                    },
                )
            )
        else:
            UI.success(f"Wrote vhost to {out}.")
        return EX_OK

    # ─── apply (SEVERE) ─────────────────────────────────────────────

    def apply(self, *, name: str, source: Path, dry_run: bool = False) -> int:
        """Copy ``source`` to ``sites-available/<name>``, symlink into
        ``sites-enabled/``, run ``nginx -s reload``.

        Caller is responsible for the SEVERE token check at the
        command layer. This method assumes authorisation has been
        granted.
        """
        cfg = get_config().tools.web.nginx
        avail_dir = Path(cfg.sites_available_dir)
        enabled_dir = Path(cfg.sites_enabled_dir)
        avail_path = avail_dir / name
        enabled_path = enabled_dir / name

        if not source.is_file():
            UI.error(f"Source vhost file not found: {source}")
            return EX_FAIL
        body = source.read_text(encoding="utf-8", errors="replace")
        if cfg.managed_marker not in body:
            UI.error(
                f"Refusing to apply {source}: missing managed marker "
                f"({cfg.managed_marker!r}). Generate via "
                f"`shimkit web nginx vhost generate` first."
            )
            return EX_FAIL

        # Refuse to overwrite a non-shimkit-managed vhost already at
        # the target. Same marker check.
        if avail_path.exists():
            try:
                existing = avail_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                existing = ""
            if cfg.managed_marker not in existing:
                UI.error(
                    f"Refusing to overwrite {avail_path}: it doesn't have "
                    f"the managed marker. Move it aside first."
                )
                return EX_FAIL

        if dry_run:
            UI.info(
                f"--dry-run: would install {source} → {avail_path}, "
                f"symlink {enabled_path} → {avail_path}, reload nginx."
            )
            return EX_OK

        if not self._atomic_install(source, avail_path):
            UI.error("install failed; see above.")
            return EX_FAIL
        if not self._symlink(avail_path, enabled_path):
            UI.error("symlink failed; vhost installed but not enabled.")
            return EX_FAIL
        if not self._reload(cfg.reload_cmd):
            UI.warning(
                "vhost installed and enabled but `nginx -s reload` "
                "failed. Run `nginx -t` to find the syntax error."
            )
            return EX_FAIL
        UI.success(f"Applied {name} → {enabled_path}")
        return EX_OK

    # ─── remove (SEVERE) ────────────────────────────────────────────

    def remove(self, *, name: str, dry_run: bool = False) -> int:
        cfg = get_config().tools.web.nginx
        avail_path = Path(cfg.sites_available_dir) / name
        enabled_path = Path(cfg.sites_enabled_dir) / name

        # Marker check: if the file is there but not managed by shimkit,
        # refuse — even with the severe token. Reduces blast radius.
        if avail_path.exists():
            try:
                body = avail_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                body = ""
            if cfg.managed_marker not in body:
                UI.error(f"Refusing to remove {avail_path}: no managed marker.")
                return EX_FAIL

        if dry_run:
            UI.info(
                f"--dry-run: would unlink {enabled_path} (if present) "
                f"and remove {avail_path} (if present), then reload nginx."
            )
            return EX_OK

        removed_any = False
        if enabled_path.exists() or enabled_path.is_symlink():
            r = CommandRunner.run(
                [*sudo_prefix(), "rm", "-f", str(enabled_path)],
                capture_output=True,
            )
            if not r.ok:
                _LOG.warning("unlink %s failed: %s", enabled_path, r.stderr)
            else:
                removed_any = True
        if avail_path.exists():
            r = CommandRunner.run(
                [*sudo_prefix(), "rm", "-f", str(avail_path)],
                capture_output=True,
            )
            if not r.ok:
                _LOG.warning("remove %s failed: %s", avail_path, r.stderr)
            else:
                removed_any = True

        if not removed_any:
            UI.info(f"{name} was not installed; nothing to remove.")
            return EX_OK

        if not self._reload(cfg.reload_cmd):
            UI.warning("vhost files removed but `nginx -s reload` failed.")
            return EX_FAIL
        UI.success(f"Removed {name}.")
        return EX_OK

    # ─── list ───────────────────────────────────────────────────────

    def list_vhosts(self, *, json_out: bool = False) -> int:
        cfg = get_config().tools.web.nginx
        enabled = Path(cfg.sites_enabled_dir)
        rows: list[dict[str, str | bool]] = []
        if enabled.is_dir():
            for entry in sorted(enabled.iterdir()):
                target = entry.resolve() if entry.is_symlink() else entry
                managed = False
                try:
                    body = target.read_text(encoding="utf-8", errors="replace")
                    managed = cfg.managed_marker in body
                except OSError:
                    pass
                rows.append(
                    {
                        "name": entry.name,
                        "target": str(target),
                        "managed": managed,
                    }
                )
        if json_out:
            emit_json(
                Event(
                    tool="web.nginx",
                    step="vhost.list",
                    status="ok",
                    data={
                        "sites_enabled_dir": str(enabled),
                        "entries": rows,
                    },
                )
            )
            return EX_OK
        if not rows:
            UI.info(f"No vhosts enabled at {enabled}.")
            return EX_OK
        UI.header(f"nginx vhosts ({len(rows)}) — {enabled}")
        for r in rows:
            tag = "shimkit" if r["managed"] else "external"
            UI.line(f"  [{tag:8s}] {r['name']:20s} → {r['target']}")
        return EX_OK

    # ─── internals ──────────────────────────────────────────────────

    def _atomic_install(self, src: Path, dst: Path) -> bool:
        """``sudo install -m 0644 -o root`` with a Python direct-write
        fallback for bind-mounted destinations (containers).
        Mirrors the pattern from ``shimkit hosts`` and ``adguard.resolv``.
        """
        fd, tmp = tempfile.mkstemp(prefix="shimkit-vhost-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(src.read_text(encoding="utf-8", errors="replace"))
            r = CommandRunner.run(
                [
                    *sudo_prefix(),
                    "install",
                    "-m",
                    "0644",
                    "-o",
                    "root",
                    tmp,
                    str(dst),
                ],
                capture_output=True,
            )
            if r.ok:
                return True
            if is_root():
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_text(
                        src.read_text(encoding="utf-8", errors="replace"),
                        encoding="utf-8",
                    )
                    return True
                except OSError as exc:
                    _LOG.warning("Direct write to %s failed: %s", dst, exc)
            else:
                _LOG.warning(
                    "install of %s failed (%s); not root for fallback.",
                    dst,
                    r.stderr.strip() or "?",
                )
            return False
        finally:
            Path(tmp).unlink(missing_ok=True)

    def _symlink(self, target: Path, link: Path) -> bool:
        # `ln -sfn` is the standard idiom for "ensure this symlink
        # points here, replacing any existing symlink or file".
        r = CommandRunner.run(
            [*sudo_prefix(), "ln", "-sfn", str(target), str(link)],
            capture_output=True,
        )
        if not r.ok:
            _LOG.warning("symlink %s → %s failed: %s", link, target, r.stderr.strip())
        return r.ok

    def _reload(self, reload_cmd: list[str]) -> bool:
        if shutil.which(reload_cmd[0]) is None:
            UI.error(
                f"`{reload_cmd[0]}` is not on PATH. Install nginx or "
                f"configure `tools.web.nginx.reload_cmd`."
            )
            return False
        r = CommandRunner.run([*sudo_prefix(), *reload_cmd], capture_output=True)
        if not r.ok:
            _LOG.warning("reload failed: %s", r.stderr.strip() or "?")
        return r.ok
