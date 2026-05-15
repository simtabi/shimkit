"""Pure ``.env`` parser + redactor.

Grammar accepted:

- Blank lines and ``# comment`` lines preserved verbatim.
- ``KEY=value`` — value runs to EOL.
- ``KEY="value with spaces"`` — quotes preserved; escape sequences
  (``\\n``, ``\\t``, ``\\\\``, ``\\"``) decoded.
- ``KEY='single-quoted'`` — single-quoted; no escape processing.
- Trailing ``# comment`` after an unquoted value is split off and
  surfaced as ``EnvEntry.comment``.
- Lines starting with ``export `` are tolerated; the ``export``
  prefix is stripped on parse and added back on render.

We intentionally don't support variable interpolation (``${OTHER}``)
— that's a runtime concern and a dotenv-loader's job, not ours.
"""

from __future__ import annotations

import re

from .models import EnvEntry, EnvFile

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse(text: str) -> EnvFile:
    """Parse the text of a .env file into an :class:`EnvFile`."""
    items: list[EnvEntry | str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            items.append(raw)
            continue
        line = stripped
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            items.append(raw)
            continue
        key, _, rest = line.partition("=")
        key = key.strip()
        if not _KEY_RE.match(key):
            items.append(raw)
            continue
        value, quoted, comment = _split_value(rest)
        items.append(EnvEntry(key=key, value=value, quoted=quoted, comment=comment))
    return EnvFile(items=items)


def render(env: EnvFile) -> str:
    """Render an :class:`EnvFile` back to text. Round-trippable."""
    out: list[str] = []
    for it in env.items:
        if isinstance(it, str):
            out.append(it)
        else:
            out.append(_render_entry(it))
    return "\n".join(out) + ("\n" if out else "")


def diff_keys(a: EnvFile, b: EnvFile) -> dict[str, list[str]]:
    """Return ``{"only_a": [...], "only_b": [...], "differ": [...]}``."""
    a_keys = set(a.keys())
    b_keys = set(b.keys())
    differ: list[str] = []
    for k in a_keys & b_keys:
        ea = a.find(k)
        eb = b.find(k)
        assert ea is not None and eb is not None
        if ea.value != eb.value:
            differ.append(k)
    return {
        "only_a": sorted(a_keys - b_keys),
        "only_b": sorted(b_keys - a_keys),
        "differ": sorted(differ),
    }


# ─── redaction ──────────────────────────────────────────────────────────


def is_secret_key(name: str, pattern: str) -> bool:
    """True iff ``name`` contains any fragment listed in ``pattern``.

    ``pattern`` is the alternation form from
    ``tools.env.redact_pattern`` — passed as a regex with case-
    insensitive substring matching.
    """
    return bool(re.search(pattern, name, re.IGNORECASE))


def redact_value(value: str) -> str:
    """Replace every char with `*`, capped at 8 chars of output."""
    if not value:
        return ""
    return "*" * min(len(value), 8)


def render_redacted(env: EnvFile, *, pattern: str, reveal: bool = False) -> str:
    """Render with secret values masked unless ``reveal`` is True."""
    out: list[str] = []
    for it in env.items:
        if isinstance(it, str):
            out.append(it)
            continue
        if not reveal and is_secret_key(it.key, pattern):
            masked = EnvEntry(
                key=it.key,
                value=redact_value(it.value),
                quoted=it.quoted,
                comment=it.comment,
            )
            out.append(_render_entry(masked))
        else:
            out.append(_render_entry(it))
    return "\n".join(out) + ("\n" if out else "")


# ─── internal ──────────────────────────────────────────────────────────


def _split_value(rest: str) -> tuple[str, bool, str | None]:
    """Take the right-hand side of ``KEY=`` and return ``(value, quoted, comment)``."""
    rest = rest.strip()
    if not rest:
        return "", False, None
    # Double-quoted with escape processing.
    if rest.startswith('"'):
        return _consume_double_quoted(rest[1:])
    # Single-quoted, no escape processing.
    if rest.startswith("'"):
        end = rest.find("'", 1)
        if end < 0:
            return rest[1:], True, None
        value = rest[1:end]
        comment = _trailing_comment(rest[end + 1 :])
        return value, True, comment
    # Bare value — comment splits on first " #".
    comment = None
    if " #" in rest:
        idx = rest.find(" #")
        value = rest[:idx].rstrip()
        comment = rest[idx + 2 :].strip() or None
        return value, False, comment
    return rest, False, None


def _consume_double_quoted(rest: str) -> tuple[str, bool, str | None]:
    out: list[str] = []
    i = 0
    while i < len(rest):
        c = rest[i]
        if c == "\\" and i + 1 < len(rest):
            nxt = rest[i + 1]
            mapping = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
            out.append(mapping.get(nxt, nxt))
            i += 2
            continue
        if c == '"':
            tail = rest[i + 1 :]
            return "".join(out), True, _trailing_comment(tail)
        out.append(c)
        i += 1
    # Unterminated quote — treat as raw.
    return "".join(out), True, None


def _trailing_comment(tail: str) -> str | None:
    tail = tail.lstrip()
    if tail.startswith("#"):
        return tail[1:].strip() or None
    return None


def _render_entry(e: EnvEntry) -> str:
    if e.quoted:
        # Re-escape double-quote and backslash.
        v = e.value.replace("\\", "\\\\").replace('"', '\\"')
        body = f'{e.key}="{v}"'
    else:
        body = f"{e.key}={e.value}"
    if e.comment:
        body = f"{body}  # {e.comment}"
    return body
