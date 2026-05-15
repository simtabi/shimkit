"""Typed value objects for ``shimkit gpg``."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GpgKey:
    """One primary key from ``gpg --list-keys --with-colons``."""

    key_id: str  # long form, e.g. "ABCD1234EF567890"
    fingerprint: str  # 40-char hex
    key_type: str  # "ed25519", "rsa3072", "rsa4096", "?"
    bits: int  # 256 for ed25519, 3072/4096 for rsa
    created: str  # ISO date "YYYY-MM-DD"
    expires: str | None  # "YYYY-MM-DD" or None (never expires)
    uids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def primary_uid(self) -> str | None:
        return self.uids[0] if self.uids else None

    @property
    def is_expired(self) -> bool:
        if self.expires is None:
            return False
        from datetime import date

        try:
            return date.fromisoformat(self.expires) < date.today()
        except ValueError:
            return False
