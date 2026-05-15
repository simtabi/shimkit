"""GpgManager — orchestrator for ``shimkit gpg``.

Owns the ``CommandRunner`` shell-outs to ``gpg`` and ``git``. Pure
parser logic lives in :mod:`shimkit.tools.gpg.parser`. Passphrases
are never handled by shimkit — ``gpg --quick-gen-key`` reads them
directly from the TTY.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from shimkit.config import get_config
from shimkit.core import UI, CommandRunner, Event, Menu, Platform, emit_json, get_logger

from . import parser as _parser
from .models import GpgKey

_LOG = get_logger("gpg")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69

# gpg accepts a short list of `--quick-gen-key` algorithm names. We map
# the friendly names users type to those.
_KEY_TYPE_TO_GPG: dict[str, str] = {
    "ed25519": "ed25519",
    "rsa4096": "rsa4096",
    "rsa3072": "rsa3072",
}


class GpgManager:
    def __init__(self) -> None:
        self._platform: Platform | None = None

    @classmethod
    def create(cls) -> GpgManager:
        return cls()

    def boot(self) -> GpgManager:
        self._platform = Platform.detect()
        if not (self._platform.is_macos or self._platform.is_linux):
            UI.error(
                f"shimkit gpg targets macOS and Linux. Detected platform: {self._platform.system}."
            )
            sys.exit(EX_UNAVAILABLE)
        if shutil.which("gpg") is None:
            UI.error(
                "`gpg` not on PATH. Install GnuPG (macOS: `brew install "
                "gnupg`; Linux: `apt install gnupg`) and retry."
            )
            sys.exit(EX_UNAVAILABLE)
        return self

    # ─── keys ──────────────────────────────────────────────────────────

    def keys_list(self, *, json_out: bool = False) -> int:
        keys = self._list_keys()
        if json_out:
            emit_json(
                Event(
                    tool="gpg",
                    step="keys.list",
                    status="ok",
                    data={
                        "keys": [
                            {
                                "key_id": k.key_id,
                                "fingerprint": k.fingerprint,
                                "type": k.key_type,
                                "bits": k.bits,
                                "created": k.created,
                                "expires": k.expires,
                                "expired": k.is_expired,
                                "uids": list(k.uids),
                            }
                            for k in keys
                        ]
                    },
                )
            )
            return EX_OK
        if not keys:
            UI.info("No GPG keys found. Generate one with `shimkit gpg keys generate`.")
            return EX_OK
        UI.header(f"GPG keys ({len(keys)})")
        for k in keys:
            uid = k.primary_uid or "(no UID)"
            tag = "  EXPIRED" if k.is_expired else ""
            UI.line(f"  {k.key_type:8s} {k.key_id}  exp={k.expires or 'never'}{tag}")
            UI.dim(f"    {uid}")
        return EX_OK

    def keys_generate(
        self,
        name: str,
        email: str,
        *,
        key_type: str | None = None,
        expiry: str | None = None,
        dry_run: bool = False,
    ) -> int:
        """Generate a new GPG key via ``gpg --quick-gen-key``.

        `name <email>` becomes the user-id. Passphrase is read by gpg
        from the TTY — we never see it.
        """
        cfg = get_config().tools.gpg
        ktype = key_type or cfg.default_key_type
        if ktype not in _KEY_TYPE_TO_GPG:
            UI.error(f"Unknown key type {ktype!r}. Allowed: {', '.join(sorted(_KEY_TYPE_TO_GPG))}.")
            return EX_FAIL
        gpg_alg = _KEY_TYPE_TO_GPG[ktype]
        uid = f"{name} <{email}>"
        expiry_v = expiry or cfg.default_key_expiry
        args = [
            "gpg",
            "--quick-gen-key",
            "--batch",
            "--passphrase",
            "",  # gpg requires --passphrase even when empty; user
            # supplies via TTY when prompted.
            uid,
            gpg_alg,
            "sign",
            expiry_v,
        ]
        if dry_run:
            UI.info(f"--dry-run: would run `gpg --quick-gen-key {uid} {gpg_alg} sign {expiry_v}`.")
            return EX_OK
        # capture_output=False so any TTY prompts (e.g. pinentry) reach the user.
        r = CommandRunner.run(args, capture_output=False)
        if not r.ok:
            UI.error(f"gpg --quick-gen-key exited {r.returncode}.")
            return EX_FAIL
        UI.success(f"Generated GPG key for {uid}.")
        return EX_OK

    def keys_export(self, key_id: str, dest: Path | None, *, dry_run: bool = False) -> int:
        """Export ``key_id``'s ASCII-armoured public key.

        Writes to ``dest`` if given, else stdout.
        """
        args = ["gpg", "--armor", "--export", key_id]
        if dry_run:
            UI.info(f"--dry-run: would run `gpg --armor --export {key_id}`.")
            return EX_OK
        r = CommandRunner.run(args)
        if not r.ok or not r.stdout.strip():
            UI.error(f"gpg --export failed for {key_id} (rc={r.returncode}).")
            return EX_FAIL
        if dest is None:
            UI.line(r.stdout)
        else:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(r.stdout, encoding="utf-8")
            except OSError as exc:
                UI.error(f"Could not write {dest}: {exc}")
                return EX_FAIL
            UI.success(f"Wrote public key to {dest}.")
        return EX_OK

    # ─── agent ─────────────────────────────────────────────────────────

    def agent_status(self, *, json_out: bool = False) -> int:
        r = CommandRunner.run(["gpg-connect-agent", "/bye"])
        agent_up = r.ok
        if json_out:
            emit_json(
                Event(
                    tool="gpg",
                    step="agent.status",
                    status="ok" if agent_up else "warning",
                    data={"agent_running": agent_up},
                )
            )
            return EX_OK if agent_up else EX_FAIL
        if agent_up:
            UI.success("gpg-agent is responding.")
            return EX_OK
        UI.warning("gpg-agent is not reachable.")
        UI.dim("Try `gpgconf --launch gpg-agent` or restart your shell.")
        return EX_FAIL

    # ─── git-signing ───────────────────────────────────────────────────

    def git_signing_show(self, *, json_out: bool = False) -> int:
        if not _check_git_or_warn():
            return EX_UNAVAILABLE
        r = CommandRunner.run(
            ["git", "config", "--global", "--get-regexp", r"^(user|commit|gpg)\."]
        )
        # `git config --get-regexp` exits 1 when nothing matches — not
        # an error from our perspective.
        cfg = _parser.parse_git_signing_config(r.stdout)
        if json_out:
            emit_json(
                Event(
                    tool="gpg",
                    step="git_signing.show",
                    status="ok",
                    data={"config": cfg},
                )
            )
            return EX_OK
        UI.header("git global signing config")
        for k, v in cfg.items():
            UI.line(f"  {k:18s} {v or '(unset)'}")
        return EX_OK

    def git_signing_configure(
        self,
        key_id: str,
        *,
        scope: str = "global",
        dry_run: bool = False,
    ) -> int:
        """Set ``user.signingkey`` + ``commit.gpgsign=true`` for git.

        ``scope`` is ``"global"`` (default) or ``"local"`` (this repo
        only). Caller already prompted MODERATE-tier.
        """
        if not _check_git_or_warn():
            return EX_UNAVAILABLE
        if scope not in {"global", "local"}:
            UI.error(f"Unknown scope {scope!r}. Use 'global' or 'local'.")
            return EX_FAIL
        flag = f"--{scope}"
        cmds = [
            ["git", "config", flag, "user.signingkey", key_id],
            ["git", "config", flag, "commit.gpgsign", "true"],
        ]
        if dry_run:
            for c in cmds:
                UI.info("--dry-run: would run `" + " ".join(c) + "`.")
            return EX_OK
        for c in cmds:
            r = CommandRunner.run(c)
            if not r.ok:
                UI.error(f"`{' '.join(c)}` failed: {r.stderr.strip()}")
                return EX_FAIL
        UI.success(f"git ({scope}) will sign commits with {key_id}.")
        return EX_OK

    # ─── interactive ──────────────────────────────────────────────────

    def run(self) -> None:
        while True:
            picked = Menu.select(
                "shimkit gpg",
                [
                    "List keys",
                    "gpg-agent status",
                    "Show git signing config",
                    "Quit",
                ],
            )
            if picked is None or picked == "Quit":
                return
            if picked == "List keys":
                self.keys_list()
            elif picked == "gpg-agent status":
                self.agent_status()
            elif picked == "Show git signing config":
                self.git_signing_show()

    # ─── internal ──────────────────────────────────────────────────────

    def _list_keys(self) -> list[GpgKey]:
        r = CommandRunner.run(["gpg", "--with-colons", "--list-keys"])
        if not r.ok:
            _LOG.warning("gpg --list-keys returned %s; stderr=%r", r.returncode, r.stderr)
            return []
        return _parser.parse_list_keys(r.stdout)


def _check_git_or_warn() -> bool:
    """Verify ``git`` is present. Surface the platform-specific
    install hint from the version-constraint registry's remediation
    table on failure so the UX matches the other tools.

    Returns True iff git is present. ``git_signing_*`` only invokes
    ``git config``; we don't enforce a version constraint here.
    """
    if shutil.which("git") is not None:
        return True
    from shimkit.core.version import _remediation_for

    UI.error("`git` is not on PATH.")
    hint = _remediation_for("git")
    if hint:
        UI.dim(f"  -> {hint}")
    return False
