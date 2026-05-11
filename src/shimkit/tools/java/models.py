"""Java version metadata and installation records.

JavaVersion mirrors a single config-entry; JavaVersion.all() returns the
list defined in ``config.tools.java.supported_versions``. The legacy
class-level ``SUPPORTED`` dict is gone — config is the source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass

from shimkit.config import get_config


@dataclass(frozen=True)
class JavaVersion:
    """Metadata for one supported OpenJDK version."""

    major: int
    label: str
    brew_formula: str
    lts: bool = False
    recommended: bool = False
    deprecated: bool = False

    def __str__(self) -> str:
        return f"Java {self.major} ({self.label})" if self.label else f"Java {self.major}"

    @property
    def number(self) -> str:
        """String form of the major version, for backward-compatible lookups."""
        return str(self.major)

    @classmethod
    def all(cls) -> list[JavaVersion]:
        """Return every supported version from the config layer."""
        return [
            cls(
                major=e.major,
                label=e.label,
                brew_formula=e.brew_formula,
                lts=e.lts,
                recommended=e.recommended,
                deprecated=e.deprecated,
            )
            for e in get_config().tools.java.supported_versions
        ]

    @classmethod
    def by_major(cls, major: int) -> JavaVersion | None:
        for v in cls.all():
            if v.major == major:
                return v
        return None


@dataclass(frozen=True)
class JavaInstallation:
    """Read-only record for a single discovered Java installation."""

    kind: str
    version: str
    path: str
    active: bool = False

    def __str__(self) -> str:
        marker = "  ✓ active" if self.active else ""
        return f"[{self.kind}] {self.version}{marker}"
