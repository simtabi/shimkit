"""Pure ``/etc/hosts`` model + parser.

Atomic-write semantics live in :mod:`shimkit.tools.hosts.manager`; this
module is just text in → typed model out, model → text. No I/O here.

The hosts-file format is forgiving:

- Whitespace-separated columns: ``<ip> <name> [name ...]``
- ``#`` starts a comment; trailing comments survive a round-trip.
- Blank lines preserved.
- Multiple names on one line are normalised to one Entry per name so
  ``HostsFile.find(name)`` can return a single result; the
  serialiser merges adjacent entries with the same IP back into one
  line on output to stay diff-friendly with hand-edited files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Strict-ish IPv4 + IPv6 regex — we use it for validating user input
# on ``hosts add``, not for parsing /etc/hosts (the file itself can
# have anything in the IP column and we should preserve it verbatim).
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_IPV6_RE = re.compile(r"^[0-9a-fA-F:]+$")


def is_valid_ip(s: str) -> bool:
    """Accept dotted-quad IPv4 or a colon-form IPv6 literal."""
    if _IPV4_RE.match(s):
        parts = s.split(".")
        return all(0 <= int(p) <= 255 for p in parts)
    return bool(_IPV6_RE.match(s) and ":" in s)


@dataclass(frozen=True)
class Entry:
    """One ``<ip> <name>`` mapping with an optional inline comment."""

    ip: str
    name: str
    comment: str | None = None  # trailing "# foo" text, sans the leading "#"

    def render(self) -> str:
        line = f"{self.ip}\t{self.name}"
        if self.comment:
            line = f"{line}\t# {self.comment}"
        return line


@dataclass
class HostsFile:
    """Parsed view of a hosts file. Lines preserved for round-trip."""

    # Mixed list: each element is either an Entry or a raw string
    # (blank line, comment-only line, or a header we should preserve).
    items: list[Entry | str] = field(default_factory=list)

    # ---- parse / render -------------------------------------------------

    @classmethod
    def parse(cls, text: str) -> HostsFile:
        items: list[Entry | str] = []
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                items.append(raw)
                continue
            # Split off trailing comment.
            comment: str | None = None
            data = raw
            if "#" in raw:
                head, _, tail = raw.partition("#")
                comment = tail.strip() or None
                data = head
            parts = data.split()
            if len(parts) < 2:
                items.append(raw)
                continue
            ip, *names = parts
            for name in names:
                items.append(Entry(ip=ip, name=name, comment=comment))
                # Comment only attaches to the first name on a shared line.
                comment = None
        return cls(items=items)

    def render(self) -> str:
        # Group adjacent same-IP entries with the same trailing comment
        # back into one line so the rendered file looks idiomatic.
        out_lines: list[str] = []
        i = 0
        while i < len(self.items):
            item = self.items[i]
            if isinstance(item, str):
                out_lines.append(item)
                i += 1
                continue
            # Greedy gather: next adjacent entries sharing ip+comment.
            ip = item.ip
            comment = item.comment
            names = [item.name]
            j = i + 1
            while j < len(self.items):
                nxt = self.items[j]
                if isinstance(nxt, Entry) and nxt.ip == ip and nxt.comment == comment:
                    names.append(nxt.name)
                    j += 1
                else:
                    break
            line = f"{ip}\t{' '.join(names)}"
            if comment:
                line = f"{line}\t# {comment}"
            out_lines.append(line)
            i = j
        return "\n".join(out_lines) + ("\n" if out_lines else "")

    # ---- queries --------------------------------------------------------

    def entries(self) -> list[Entry]:
        return [it for it in self.items if isinstance(it, Entry)]

    def find(self, name: str) -> list[Entry]:
        return [e for e in self.entries() if e.name == name]

    def has(self, name: str) -> bool:
        return any(e.name == name for e in self.entries())

    # ---- mutators -------------------------------------------------------

    def add(self, ip: str, name: str, *, comment: str | None = None) -> bool:
        """Append. Returns True iff the line wasn't already present."""
        for e in self.entries():
            if e.ip == ip and e.name == name:
                return False
        self.items.append(Entry(ip=ip, name=name, comment=comment))
        return True

    def remove(self, name: str) -> int:
        """Remove every entry matching ``name``. Returns count removed."""
        before = len(self.items)
        self.items = [it for it in self.items if not (isinstance(it, Entry) and it.name == name)]
        return before - len(self.items)


def parse_block_list(text: str) -> list[tuple[str, str]]:
    """Parse a StevenBlack-style block list.

    Each non-comment line is expected to be ``<ip> <name>`` (typically
    ``0.0.0.0 example.com``). Anything else is skipped. Returns
    ``[(ip, name), ...]`` deduplicated by name.
    """
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        ip, name = parts[0], parts[1]
        if not is_valid_ip(ip):
            continue
        if name in seen:
            continue
        seen.add(name)
        out.append((ip, name))
    return out
