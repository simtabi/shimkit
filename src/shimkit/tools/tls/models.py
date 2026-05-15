"""Plain-data structures for ``shimkit tls``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CertInfo:
    """One row in `shimkit tls list`.

    Drawn from the on-disk Let's Encrypt layout under
    ``<data_dir>/etc-letsencrypt/live/<domain>/`` and the cert's own
    ``notAfter`` field (read via `openssl x509 -enddate`).
    """

    domain: str
    fullchain_path: str
    privkey_path: str
    expires_at: datetime | None
    days_remaining: int | None

    @property
    def expiring_soon(self) -> bool:
        """Within 30 days of expiry — the Let's Encrypt renewal window."""
        return self.days_remaining is not None and self.days_remaining < 30
