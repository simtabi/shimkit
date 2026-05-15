"""Pure I/O + parser helpers for ``shimkit ssh``.

The Manager owns ``CommandRunner`` shell-outs (ssh-keygen, ssh-add,
…). This module is responsible for filesystem reads + the
``known_hosts`` / ``ssh -G`` parsers. Functions are written to be
called against an arbitrary ``ssh_dir`` so tests can target a
tmp_path.
"""

from __future__ import annotations

import re
import stat
from collections import defaultdict
from pathlib import Path

from .models import KeyEntry, PermIssue

# Recognised private-key filenames. Public counterparts are simply the
# same name with ``.pub`` appended.
_KNOWN_KEY_NAMES = (
    "id_ed25519",
    "id_rsa",
    "id_ecdsa",
    "id_dsa",
)

_AGENT_KEY_RE = re.compile(r"^(?P<type>\S+)\s+(?P<key>\S+)(?:\s+(?P<comment>.+))?$")


def list_keys(ssh_dir: Path) -> list[KeyEntry]:
    """Walk ``ssh_dir`` and return one ``KeyEntry`` per private key.

    A key is "private" if (a) it has one of the known names, or (b)
    its OpenSSH header line is ``-----BEGIN OPENSSH PRIVATE KEY-----``
    (most modern keys) or one of the legacy header forms.
    """
    if not ssh_dir.is_dir():
        return []
    found: list[KeyEntry] = []
    for entry in sorted(ssh_dir.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix == ".pub":
            continue
        if entry.name in _KNOWN_KEY_NAMES or _looks_like_private_key(entry):
            pub = (
                entry.with_suffix(entry.suffix + ".pub")
                if entry.suffix
                else (entry.parent / f"{entry.name}.pub")
            )
            key_type, comment = (
                _read_pub_metadata(pub)
                if pub.is_file()
                else (
                    _key_type_from_name(entry.name),
                    None,
                )
            )
            found.append(
                KeyEntry(
                    private=entry,
                    public=pub if pub.is_file() else None,
                    key_type=key_type,
                    comment=comment,
                )
            )
    return found


def parse_agent_keys(text: str) -> list[dict[str, str | None]]:
    """Parse the output of ``ssh-add -L`` (full public keys) or
    ``ssh-add -l`` (fingerprints).

    ``-l`` shape:  ``256 SHA256:abc... user@host (ED25519)``
    ``-L`` shape:  ``ssh-ed25519 AAAA...= user@host``

    Returns dicts to keep the parser format-agnostic; the manager
    materialises ``AgentKey`` instances.
    """
    out: list[dict[str, str | None]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "The agent has no identities.":
            continue
        # Detect "-l" form by leading number.
        head = line.split(None, 1)[0]
        if head.isdigit():
            parts = line.split(None, 3)
            # bits SHA256:fp comment (TYPE)
            if len(parts) >= 3:
                fp = parts[1]
                tail = parts[2] if len(parts) == 3 else parts[2] + " " + parts[3]
                key_type = "?"
                comment: str | None = tail
                if tail.endswith(")") and "(" in tail:
                    open_paren = tail.rfind("(")
                    key_type = tail[open_paren + 1 : -1]
                    comment = tail[:open_paren].strip() or None
                out.append({"type": key_type, "fingerprint": fp, "comment": comment})
            continue
        m = _AGENT_KEY_RE.match(line)
        if m:
            out.append(
                {
                    "type": m.group("type"),
                    "fingerprint": m.group("key")[:32],
                    "comment": m.group("comment"),
                }
            )
    return out


# ─── known_hosts ─────────────────────────────────────────────────────────


def parse_known_hosts(text: str) -> list[tuple[int, str, str]]:
    """Return ``[(line_no, host_field, key_blob), ...]``.

    Comment / blank lines are skipped. ``line_no`` is 0-based.
    """
    out: list[tuple[int, str, str]] = []
    for i, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        host, _key_type, key_blob = parts
        out.append((i, host, key_blob))
    return out


def find_known_host_duplicates(text: str) -> list[tuple[str, list[int]]]:
    """Return ``[(host, [line_no, line_no, ...]), ...]`` for any host
    whose key blob appears on more than one line."""
    rows = parse_known_hosts(text)
    by_host: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for line_no, host, blob in rows:
        by_host[host].append((line_no, blob))
    dupes: list[tuple[str, list[int]]] = []
    for host, entries in by_host.items():
        seen_blobs: dict[str, list[int]] = defaultdict(list)
        for line_no, blob in entries:
            seen_blobs[blob].append(line_no)
        for line_nos in seen_blobs.values():
            if len(line_nos) > 1:
                dupes.append((host, line_nos))
    return dupes


def prune_known_hosts_duplicates(text: str) -> tuple[str, int]:
    """Drop later occurrences of any (host, key_blob) tuple. Comments and
    blank lines are preserved verbatim. Returns ``(new_text, removed)``.
    """
    seen: set[tuple[str, str]] = set()
    out: list[str] = []
    removed = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            out.append(raw)
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            out.append(raw)
            continue
        host, _ktype, blob = parts
        key = (host, blob)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        out.append(raw)
    new = "\n".join(out)
    if text.endswith("\n"):
        new = new + "\n" if not new.endswith("\n") else new
    return new, removed


# ─── perms ───────────────────────────────────────────────────────────────


def audit_perms(
    ssh_dir: Path,
    *,
    perms_dir: str = "700",
    perms_private: str = "600",
    perms_public: str = "644",
    perms_known: str = "644",
    perms_authorized: str = "644",
    perms_config: str = "644",
) -> list[PermIssue]:
    """Walk ``ssh_dir`` and flag every file whose mode is laxer than
    the configured maximum."""
    issues: list[PermIssue] = []
    if not ssh_dir.is_dir():
        return issues

    # The dir itself.
    issues.extend(_check_one(ssh_dir, perms_dir))

    for entry in ssh_dir.iterdir():
        if entry.is_dir():
            issues.extend(_check_one(entry, perms_dir))
            continue
        if not entry.is_file():
            continue
        name = entry.name
        if name == "config":
            issues.extend(_check_one(entry, perms_config))
        elif name == "known_hosts":
            issues.extend(_check_one(entry, perms_known))
        elif name == "authorized_keys":
            issues.extend(_check_one(entry, perms_authorized))
        elif name.endswith(".pub"):
            issues.extend(_check_one(entry, perms_public))
        elif _looks_like_private_key(entry) or name in _KNOWN_KEY_NAMES:
            issues.extend(_check_one(entry, perms_private))
        # Anything else (random files the user dropped in ~/.ssh) is
        # ignored — out of scope for shimkit.
    return issues


def expected_mode_for(entry: Path, perms: dict[str, str]) -> str:
    """Map a path to the mode it ought to have."""
    if entry.is_dir():
        return perms["dir"]
    name = entry.name
    if name == "config":
        return perms["config"]
    if name == "known_hosts":
        return perms["known_hosts"]
    if name == "authorized_keys":
        return perms["authorized_keys"]
    if name.endswith(".pub"):
        return perms["public_key"]
    return perms["private_key"]


# ─── internal ────────────────────────────────────────────────────────────


def _check_one(path: Path, expected: str) -> list[PermIssue]:
    try:
        st = path.stat()
    except OSError:
        return []
    actual = oct(stat.S_IMODE(st.st_mode))[2:].zfill(3)
    # We compare as octal-integer-as-string: a file with stricter perms
    # than expected is fine; only laxer fails.
    if int(actual, 8) & ~int(expected, 8):
        return [PermIssue(path=path, actual=actual, expected=expected)]
    return []


def _key_type_from_name(name: str) -> str:
    if "ed25519" in name:
        return "ed25519"
    if "rsa" in name:
        return "rsa"
    if "ecdsa" in name:
        return "ecdsa"
    if "dsa" in name:
        return "dsa"
    return "?"


def _read_pub_metadata(pub: Path) -> tuple[str, str | None]:
    try:
        body = pub.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ("?", None)
    parts = body.split(None, 2)
    if len(parts) < 2:
        return ("?", None)
    key_type = parts[0].removeprefix("ssh-")
    if key_type.startswith("ecdsa"):
        key_type = "ecdsa"
    comment = parts[2] if len(parts) == 3 else None
    return (key_type or "?", comment)


def _looks_like_private_key(p: Path) -> bool:
    """Cheap header sniff. Avoids reading the whole file."""
    if p.suffix == ".pub":
        return False
    try:
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(64)
    except OSError:
        return False
    return (
        "BEGIN OPENSSH PRIVATE KEY" in head
        or "BEGIN RSA PRIVATE KEY" in head
        or "BEGIN EC PRIVATE KEY" in head
        or "BEGIN DSA PRIVATE KEY" in head
        or "BEGIN PRIVATE KEY" in head
    )
