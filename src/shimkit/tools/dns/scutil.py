"""Parse ``scutil --dns`` output into :class:`ResolverChain`.

The output is a sequence of ``resolver #N { ... }`` blocks separated by
blank lines. Each block has key/value lines plus repeated ``nameserver[i]
: X.X.X.X`` and ``search domain[i] : foo.example`` lines.

Re-parsing this in Python avoids the bash bugs that the legacy script
hit: BSD ``grep -E '\\d'`` doesn't match Perl ``\\d`` and silently
falls through.
"""

from __future__ import annotations

import re

from shimkit.core import CommandRunner

from .models import Resolver, ResolverChain

_RESOLVER_RE = re.compile(r"^resolver\s+#(\d+)\s*$")
_NAMESERVER_RE = re.compile(r"^\s*nameserver\[\d+\]\s*:\s*(\S+)\s*$")
_SEARCH_RE = re.compile(r"^\s*search\s+domain\[\d+\]\s*:\s*(\S+)\s*$")
_INTERFACE_RE = re.compile(r"^\s*if_index\s*:\s*\d+\s*\((\S+)\)\s*$")
_FLAGS_RE = re.compile(r"^\s*flags\s*:\s*(.+)$")
_REACH_RE = re.compile(r"^\s*reach\s*:\s*(.+)$")


def parse(text: str) -> ResolverChain:
    """Parse the textual output of ``scutil --dns``."""
    resolvers: list[Resolver] = []
    current_idx: int | None = None
    nameservers: list[str] = []
    search: list[str] = []
    interface: str | None = None
    flags: str | None = None
    reach: str | None = None

    def flush() -> None:
        nonlocal current_idx, nameservers, search, interface, flags, reach
        if current_idx is None:
            return
        resolvers.append(
            Resolver(
                index=current_idx,
                nameservers=tuple(nameservers),
                search_domains=tuple(search),
                interface=interface,
                flags=flags,
                reach=reach,
            )
        )
        nameservers = []
        search = []
        interface = None
        flags = None
        reach = None
        current_idx = None

    for line in text.splitlines():
        m = _RESOLVER_RE.match(line)
        if m:
            flush()
            current_idx = int(m.group(1))
            continue
        if current_idx is None:
            continue
        if (m := _NAMESERVER_RE.match(line)):
            nameservers.append(m.group(1))
        elif (m := _SEARCH_RE.match(line)):
            search.append(m.group(1))
        elif (m := _INTERFACE_RE.match(line)):
            interface = m.group(1)
        elif (m := _FLAGS_RE.match(line)):
            flags = m.group(1).strip()
        elif (m := _REACH_RE.match(line)):
            reach = m.group(1).strip()

    flush()
    return ResolverChain(resolvers=tuple(resolvers))


def query() -> ResolverChain:
    """Run ``scutil --dns`` and return the parsed chain."""
    r = CommandRunner.run(["scutil", "--dns"])
    if not r.ok:
        return ResolverChain()
    return parse(r.stdout)
