"""Pure parser for ``gpg --with-colons`` output.

GnuPG's machine-readable mode emits a colon-delimited, line-per-
record stream. Field reference:
https://github.com/gpg/gnupg/blob/master/doc/DETAILS

Records we care about:

- ``pub`` — primary public key. Fields: type, validity, length, algo,
  keyid, creation, expiry, …
- ``fpr`` — fingerprint of the immediately preceding key record.
- ``uid`` — user-id string (name + email).

The parser is intentionally tolerant of unknown record types so
future GnuPG releases that add fields don't break us.
"""

from __future__ import annotations

from datetime import datetime

from .models import GpgKey

# Map gpg's numeric algo IDs to friendly names. Reference: doc/DETAILS.
_ALGO_NAMES: dict[int, str] = {
    1: "rsa",  # rsa-encrypt-or-sign
    17: "dsa",
    18: "ecdh",
    19: "ecdsa",
    22: "ed25519",
}


def parse_list_keys(text: str) -> list[GpgKey]:
    """Parse the output of ``gpg --with-colons --list-keys``."""
    keys: list[GpgKey] = []
    # Narrow types so mypy doesn't have to widen everything to ``object``.
    cur_key_id: str = ""
    cur_fpr: str = ""
    cur_type: str = "?"
    cur_bits: int = 0
    cur_created: str = ""
    cur_expires: str | None = None
    open_record = False
    uids: list[str] = []

    def flush() -> None:
        nonlocal uids
        if not open_record:
            return
        keys.append(
            GpgKey(
                key_id=cur_key_id,
                fingerprint=cur_fpr,
                key_type=cur_type,
                bits=cur_bits,
                created=cur_created,
                expires=cur_expires,
                uids=tuple(uids),
            )
        )
        uids = []

    for raw in text.splitlines():
        if not raw:
            continue
        parts = raw.split(":")
        rec = parts[0]
        if rec == "pub":
            flush()
            open_record = True
            algo_id = _maybe_int(parts[3])
            bits = _maybe_int(parts[2])
            cur_key_id = parts[4] if len(parts) > 4 else ""
            cur_created = _ts_to_date(parts[5] if len(parts) > 5 else "")
            cur_expires = _ts_to_date(parts[6] if len(parts) > 6 else "") or None
            cur_type = _ALGO_NAMES.get(algo_id or 0, "?")
            cur_bits = bits or 0
            cur_fpr = ""
        elif rec == "fpr" and open_record:
            cur_fpr = parts[9] if len(parts) > 9 else ""
        elif rec == "uid" and open_record:
            uid = parts[9] if len(parts) > 9 else ""
            if uid:
                uids.append(uid)

    flush()
    return keys


def _maybe_int(s: str) -> int | None:
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _ts_to_date(s: str) -> str:
    """gpg --with-colons gives a unix epoch or ISO timestamp. Normalise to YYYY-MM-DD.

    A literal ``"0"`` in the expiry field means "never expires" — return
    empty string so the caller (which uses ``... or None``) maps it to None.
    """
    if not s or s == "0":
        return ""
    try:
        return datetime.fromtimestamp(int(s)).date().isoformat()
    except (TypeError, ValueError):
        # Already ISO-ish? Take the first 10 chars.
        return s[:10] if len(s) >= 10 else s


# ─── git-config helpers ─────────────────────────────────────────────────


def parse_git_signing_config(stdout: str) -> dict[str, str | None]:
    """Parse the output of ``git config --get-regexp '^(user|commit)\\.'``.

    Returns a dict keyed by the config name. Missing keys map to None
    so callers can compare against expected state.
    """
    out: dict[str, str | None] = {
        "user.signingkey": None,
        "commit.gpgsign": None,
        "gpg.format": None,
    }
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        name, _, value = line.partition(" ")
        if name in out:
            out[name] = value or None
    return out
