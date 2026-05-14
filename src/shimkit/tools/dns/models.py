"""Typed value objects for ``shimkit dns``."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Resolver:
    """One resolver from ``scutil --dns`` output."""

    index: int
    nameservers: tuple[str, ...] = ()
    search_domains: tuple[str, ...] = ()
    interface: str | None = None
    flags: str | None = None
    reach: str | None = None

    @property
    def is_tailscale(self) -> bool:
        """100.100.100.100 is Tailscale MagicDNS."""
        return "100.100.100.100" in self.nameservers


@dataclass(frozen=True)
class ResolverChain:
    """Parsed ``scutil --dns`` snapshot — every resolver in order."""

    resolvers: tuple[Resolver, ...] = ()

    @property
    def primary_nameservers(self) -> tuple[str, ...]:
        if not self.resolvers:
            return ()
        return self.resolvers[0].nameservers


@dataclass(frozen=True)
class NetworkService:
    """One row from ``networksetup -listallhardwareports``."""

    name: str
    device: str
    is_wifi: bool


@dataclass(frozen=True)
class FixStep:
    """One step in the 6-step recovery escalation."""

    number: int
    name: str
    description: str


@dataclass
class FixResult:
    """Outcome of running one fix step."""

    step: FixStep
    applied: bool = False
    resolved: bool = False
    notes: list[str] = field(default_factory=list)
