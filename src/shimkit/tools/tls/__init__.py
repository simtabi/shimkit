"""``shimkit tls`` -- TLS certificate lifecycle helper.

Container-first: runs upstream `certbot/certbot` one-shot for issue
/ renew / revoke, persisting `/etc/letsencrypt` to
``~/.shimkit/data/tls/`` so state survives container restarts.
Hands the resulting certs off to nginx via well-known paths;
renewal is wired through ``shimkit cron``.
"""

from __future__ import annotations

from .manager import TlsManager

__all__ = ["TlsManager"]
