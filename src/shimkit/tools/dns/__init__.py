"""macOS DNS resolver recovery — ``shimkit dns``.

Ported from ``shell-scripts/fixdns.sh``. The bash version had bugs that
this port fixes: BSD ``grep -E '\\d'`` failure in ``detect_service``;
multi-byte spinner indexing; ``timeout(1)`` dependency that isn't on
stock macOS; sudo-keepalive trap race; Wi-Fi-power-cycle on non-Wi-Fi
interfaces. See ``docs/tools/dns.md`` for the full origin notes.
"""

from __future__ import annotations

from .manager import DnsManager
from .models import Resolver, ResolverChain

__all__ = ["DnsManager", "Resolver", "ResolverChain"]
