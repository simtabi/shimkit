"""SshManager — orchestrator for ``shimkit ssh``.

Owns the ``CommandRunner`` shell-outs to ``ssh-keygen``, ``ssh-add``,
``ssh-agent``, and ``ssh-keyscan``. Pure filesystem + parser logic
lives in :mod:`shimkit.tools.ssh.scanner`.

The SSH dir is injectable via ``boot(ssh_dir_override=...)`` so tests
can target a tmp_path without writing into the developer's real
``~/.ssh``.
"""

from __future__ import annotations

import os
import sys
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
)

from . import scanner

_LOG = get_logger("ssh")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69


class SshManager:
    def __init__(self) -> None:
        self._platform: Platform | None = None
        self._ssh_dir: Path | None = None

    @classmethod
    def create(cls) -> SshManager:
        return cls()

    def boot(self, *, ssh_dir_override: Path | None = None) -> SshManager:
        self._platform = Platform.detect()
        if not (self._platform.is_macos or self._platform.is_linux):
            UI.error(
                f"shimkit ssh targets macOS and Linux. Detected platform: {self._platform.system}."
            )
            sys.exit(EX_UNAVAILABLE)
        cfg = get_config().tools.ssh
        ssh_dir = ssh_dir_override or Path(cfg.ssh_dir).expanduser()
        self._ssh_dir = ssh_dir
        return self

    # ─── keys ──────────────────────────────────────────────────────────

    def keys_list(self, *, json_out: bool = False) -> int:
        assert self._ssh_dir is not None
        keys = scanner.list_keys(self._ssh_dir)
        if json_out:
            emit_json(
                Event(
                    tool="ssh",
                    step="keys.list",
                    status="ok",
                    data={
                        "ssh_dir": str(self._ssh_dir),
                        "keys": [
                            {
                                "name": k.name,
                                "type": k.key_type,
                                "public": str(k.public) if k.public else None,
                                "comment": k.comment,
                            }
                            for k in keys
                        ],
                    },
                )
            )
            return EX_OK
        if not keys:
            UI.info(f"No keys in {self._ssh_dir}.")
            return EX_OK
        UI.header(f"SSH keys ({len(keys)}) — {self._ssh_dir}")
        for k in keys:
            pub_tag = " (no .pub)" if k.public is None else ""
            comment = f"  # {k.comment}" if k.comment else ""
            UI.line(f"  {k.key_type:8s} {k.name}{pub_tag}{comment}")
        return EX_OK

    def keys_generate(
        self,
        name: str,
        *,
        key_type: str | None = None,
        comment: str | None = None,
        dry_run: bool = False,
    ) -> int:
        """Generate a new key pair via ``ssh-keygen -t <type>``.

        Passphrase is read interactively by ssh-keygen itself — we
        never handle or log it. The caller (Typer command) is
        responsible for the MODERATE-tier prompt.
        """
        assert self._ssh_dir is not None
        cfg = get_config().tools.ssh
        ktype = key_type or cfg.default_key_type
        target = self._ssh_dir / name
        if target.exists():
            UI.error(
                f"{target} already exists. Pick a different name or use "
                "`keys rotate` to replace it with a backup."
            )
            return EX_FAIL
        if dry_run:
            UI.info(f"--dry-run: would run `ssh-keygen -t {ktype} -f {target}`.")
            return EX_OK
        # ssh-keygen creates ~/.ssh with the right mode on first run.
        self._ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        args = ["ssh-keygen", "-t", ktype, "-f", str(target)]
        if comment:
            args.extend(["-C", comment])
        # capture_output=False so the interactive passphrase prompt
        # reaches the user's terminal.
        r = CommandRunner.run(args, capture_output=False)
        if not r.ok:
            UI.error(f"ssh-keygen exited {r.returncode}.")
            return EX_FAIL
        UI.success(f"Generated {target}")
        return EX_OK

    def keys_rotate(
        self,
        name: str,
        *,
        key_type: str | None = None,
        dry_run: bool = False,
    ) -> int:
        """Generate a new key and back the old one up alongside.

        The user is responsible for syncing the new public key to
        every authorized_keys server — we print the steps but don't
        push anywhere.
        """
        assert self._ssh_dir is not None
        target = self._ssh_dir / name
        if not target.exists():
            UI.error(f"{target} does not exist; nothing to rotate.")
            return EX_FAIL
        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        bak = target.with_name(f"{name}.bak-{ts}")
        pub = target.with_suffix(target.suffix + ".pub")
        bak_pub = pub.with_name(f"{pub.name}.bak-{ts}") if pub.exists() else None
        if dry_run:
            UI.info(f"--dry-run: would mv {target} → {bak} and regenerate.")
            if bak_pub:
                UI.info(f"--dry-run: would mv {pub} → {bak_pub}.")
            return EX_OK
        target.rename(bak)
        if bak_pub is not None:
            pub.rename(bak_pub)
        UI.info(f"Old key backed up to {bak}.")
        code = self.keys_generate(name, key_type=key_type)
        if code != EX_OK:
            return code
        UI.info("Next: copy the new public key to every server that trusts the old one:")
        UI.dim(f"  cat {target}.pub")
        UI.dim("  # paste into ~/.ssh/authorized_keys on each remote host")
        return EX_OK

    # ─── agent ─────────────────────────────────────────────────────────

    def agent_status(self, *, json_out: bool = False) -> int:
        r = CommandRunner.run(["ssh-add", "-l"])
        # `ssh-add -l` exits 0 when keys are loaded, 1 when none loaded,
        # 2 when the agent is unreachable. Don't fail-fast on 1 — that's
        # information, not an error.
        agent_up = r.returncode != 2
        keys: list[dict[str, str | None]] = []
        if agent_up:
            keys = scanner.parse_agent_keys(r.stdout)
        if json_out:
            emit_json(
                Event(
                    tool="ssh",
                    step="agent.status",
                    status="ok" if agent_up else "warning",
                    data={
                        "agent_running": agent_up,
                        "keys_loaded": len(keys),
                        "keys": keys,
                    },
                )
            )
            return EX_OK if agent_up else EX_FAIL
        if not agent_up:
            UI.warning("ssh-agent is not reachable. Run `shimkit ssh agent start`.")
            return EX_FAIL
        if not keys:
            UI.info("ssh-agent is running, no keys loaded.")
            return EX_OK
        UI.header(f"ssh-agent — {len(keys)} key(s) loaded")
        for k in keys:
            comment = f"  # {k['comment']}" if k.get("comment") else ""
            UI.line(f"  {(k.get('type') or '?'):8s} {k['fingerprint']}{comment}")
        return EX_OK

    def agent_add(self, key_path: Path, *, dry_run: bool = False) -> int:
        if not key_path.exists():
            UI.error(f"{key_path} does not exist.")
            return EX_FAIL
        if dry_run:
            UI.info(f"--dry-run: would `ssh-add {key_path}`.")
            return EX_OK
        r = CommandRunner.run(["ssh-add", str(key_path)], capture_output=False)
        return EX_OK if r.ok else EX_FAIL

    # ─── known_hosts ────────────────────────────────────────────────────

    def known_hosts_audit(self, *, json_out: bool = False) -> int:
        assert self._ssh_dir is not None
        kh = self._ssh_dir / "known_hosts"
        if not kh.is_file():
            if json_out:
                emit_json(
                    Event(
                        tool="ssh",
                        step="known_hosts.audit",
                        status="ok",
                        data={"path": str(kh), "duplicates": []},
                    )
                )
            else:
                UI.info(f"{kh} not present.")
            return EX_OK
        text = kh.read_text(encoding="utf-8", errors="replace")
        dupes = scanner.find_known_host_duplicates(text)
        if json_out:
            emit_json(
                Event(
                    tool="ssh",
                    step="known_hosts.audit",
                    status="warning" if dupes else "ok",
                    data={
                        "path": str(kh),
                        "duplicates": [{"host": h, "line_numbers": lines} for h, lines in dupes],
                    },
                )
            )
            return EX_OK
        if not dupes:
            UI.success(f"{kh}: no duplicate entries.")
            return EX_OK
        UI.warning(f"{kh}: {len(dupes)} duplicate(s)")
        for host, lines in dupes:
            UI.line(f"  {host}\tlines {lines}")
        return EX_OK

    def known_hosts_prune(self, *, dry_run: bool = False) -> int:
        assert self._ssh_dir is not None
        kh = self._ssh_dir / "known_hosts"
        if not kh.is_file():
            UI.info(f"{kh} not present; nothing to prune.")
            return EX_OK
        text = kh.read_text(encoding="utf-8", errors="replace")
        new, removed = scanner.prune_known_hosts_duplicates(text)
        if removed == 0:
            UI.info("No duplicates to prune.")
            return EX_OK
        if dry_run:
            UI.info(f"--dry-run: would prune {removed} duplicate line(s).")
            return EX_OK
        # Atomic rewrite. known_hosts is a per-user file, so a plain
        # write_text is correct (no sudo, no temp+rename gymnastics).
        kh.write_text(new, encoding="utf-8")
        UI.success(f"Pruned {removed} duplicate line(s) from {kh}.")
        return EX_OK

    # ─── perms ─────────────────────────────────────────────────────────

    def perms_audit(self, *, json_out: bool = False) -> int:
        assert self._ssh_dir is not None
        cfg = get_config().tools.ssh
        issues = scanner.audit_perms(
            self._ssh_dir,
            perms_dir=cfg.perms.dir,
            perms_private=cfg.perms.private_key,
            perms_public=cfg.perms.public_key,
            perms_known=cfg.perms.known_hosts,
            perms_authorized=cfg.perms.authorized_keys,
            perms_config=cfg.perms.config,
        )
        if json_out:
            emit_json(
                Event(
                    tool="ssh",
                    step="perms.audit",
                    status="warning" if issues else "ok",
                    data={
                        "ssh_dir": str(self._ssh_dir),
                        "issues": [
                            {
                                "path": str(i.path),
                                "actual": i.actual,
                                "expected": i.expected,
                            }
                            for i in issues
                        ],
                    },
                )
            )
            return EX_OK
        if not issues:
            UI.success(f"{self._ssh_dir}: permissions look correct.")
            return EX_OK
        UI.warning(f"{self._ssh_dir}: {len(issues)} permission issue(s)")
        for i in issues:
            UI.line(f"  {i.actual} → {i.expected}\t{i.path}")
        UI.dim("Run `shimkit ssh perms fix` to chmod each.")
        return EX_OK

    def perms_fix(self, *, dry_run: bool = False) -> int:
        assert self._ssh_dir is not None
        cfg = get_config().tools.ssh
        issues = scanner.audit_perms(
            self._ssh_dir,
            perms_dir=cfg.perms.dir,
            perms_private=cfg.perms.private_key,
            perms_public=cfg.perms.public_key,
            perms_known=cfg.perms.known_hosts,
            perms_authorized=cfg.perms.authorized_keys,
            perms_config=cfg.perms.config,
        )
        if not issues:
            UI.success("Nothing to fix.")
            return EX_OK
        if dry_run:
            UI.info(f"--dry-run: would chmod {len(issues)} path(s).")
            for i in issues:
                UI.line(f"  chmod {i.expected} {i.path}")
            return EX_OK
        fixed = 0
        for i in issues:
            try:
                os.chmod(i.path, int(i.expected, 8))
                fixed += 1
            except OSError as exc:
                UI.warning(f"chmod failed for {i.path}: {exc}")
        UI.success(f"Fixed {fixed}/{len(issues)} permission issue(s).")
        return EX_OK if fixed == len(issues) else EX_FAIL

    # ─── config ───────────────────────────────────────────────────────

    def config_show(self, host: str | None = None) -> int:
        assert self._ssh_dir is not None
        cfg_file = self._ssh_dir / "config"
        if not cfg_file.is_file():
            UI.info(f"{cfg_file} not present.")
            return EX_OK
        if host is None:
            UI.header(f"~/.ssh/config — {cfg_file}")
            UI.line(cfg_file.read_text(encoding="utf-8", errors="replace"))
            return EX_OK
        # `ssh -G HOST` expands the config for a given host. Trust the
        # local ssh binary — we already shell out for keygen, this
        # keeps the parsing logic out of our codebase.
        r = CommandRunner.run(["ssh", "-G", host])
        if not r.ok:
            UI.error(f"ssh -G {host} failed: {r.stderr.strip()}")
            return EX_FAIL
        UI.header(f"Effective config for {host}")
        UI.line(r.stdout)
        return EX_OK

    # ─── interactive ──────────────────────────────────────────────────

    def run(self) -> None:
        """Bare ``shimkit ssh`` interactive menu (read-only paths)."""
        while True:
            picked = Menu.select(
                "shimkit ssh",
                [
                    "List keys",
                    "ssh-agent status",
                    "Audit known_hosts duplicates",
                    "Audit ~/.ssh permissions",
                    "Quit",
                ],
            )
            if picked is None or picked == "Quit":
                return
            if picked == "List keys":
                self.keys_list()
            elif picked == "ssh-agent status":
                self.agent_status()
            elif picked == "Audit known_hosts duplicates":
                self.known_hosts_audit()
            elif picked == "Audit ~/.ssh permissions":
                self.perms_audit()
