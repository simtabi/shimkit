"""Typed value objects for ``shimkit ports``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PortOwner:
    """One process holding one listening (or UDP-bound) socket."""

    port: int
    proto: str  # "tcp" or "udp"
    pid: int
    name: str
    user: str | None = None
    # Cross-platform address binding — "127.0.0.1", "::", "0.0.0.0".
    # Mostly informational; not used for decisions.
    address: str | None = None

    @property
    def is_loopback(self) -> bool:
        return self.address in {"127.0.0.1", "::1"} if self.address else False

    @property
    def display(self) -> str:
        addr = f" @ {self.address}" if self.address else ""
        owner = f"{self.name}(pid={self.pid})"
        return f"{self.proto}/{self.port}{addr} → {owner}"
