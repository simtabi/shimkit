"""OS / arch / container / WSL detection for the current host."""

from __future__ import annotations

import platform as _stdlib_platform
from pathlib import Path


class Platform:
    """Detects the host OS and derives platform-dependent paths.

    Captures values from the standard ``platform`` module at construction so
    repeated calls do not hit the system. All other shimkit code routes
    through this class for OS branching, never reaching for
    ``platform.system()`` directly.
    """

    def __init__(
        self,
        system: str | None = None,
        machine: str | None = None,
    ) -> None:
        """Construct with overrides for testing; defaults to host detection.

        Tests should pass ``system=`` / ``machine=`` rather than mutating
        ``_system`` / ``_machine`` post-construction.
        """
        self._system = system if system is not None else _stdlib_platform.system()
        self._machine = machine if machine is not None else _stdlib_platform.machine()

    @classmethod
    def detect(cls) -> Platform:
        return cls()

    @property
    def system(self) -> str:
        return self._system

    @property
    def is_macos(self) -> bool:
        return self._system == "Darwin"

    @property
    def is_linux(self) -> bool:
        return self._system == "Linux"

    @property
    def is_apple_silicon(self) -> bool:
        return self.is_macos and self._machine == "arm64"

    @property
    def is_wsl(self) -> bool:
        if not self.is_linux:
            return False
        try:
            return (
                "microsoft"
                in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
            )
        except OSError:
            return False

    @property
    def is_container(self) -> bool:
        if Path("/.dockerenv").exists():
            return True
        return self._cgroup_has("docker", "lxc", "kubepods", "containerd")

    @property
    def is_supported(self) -> bool:
        """True on macOS and Linux; False on Windows or unknown OSes."""
        return self.is_macos or self.is_linux

    @property
    def brew_prefix(self) -> str:
        """Resolve the Homebrew installation prefix for this host."""
        if self.is_apple_silicon:
            return "/opt/homebrew"
        if self.is_macos:
            return "/usr/local"
        for candidate in (
            "/home/linuxbrew/.linuxbrew",
            str(Path.home() / ".linuxbrew"),
        ):
            if Path(candidate).exists():
                return candidate
        return "/home/linuxbrew/.linuxbrew"

    @property
    def jvm_base(self) -> Path:
        """The standard system JVM installation directory for this OS."""
        if self.is_macos:
            return Path("/Library/Java/JavaVirtualMachines")
        return Path("/usr/lib/jvm")

    @property
    def os_key(self) -> str:
        """Stable key for indexing OS-keyed config sections (e.g. scan_paths)."""
        if self.is_macos:
            return "macos"
        if self.is_linux:
            return "linux"
        return "unknown"

    @property
    def description(self) -> str:
        arch = "Apple Silicon" if self.is_apple_silicon else self._machine
        name = "macOS" if self.is_macos else "Linux"
        tags: list[str] = []
        if self.is_wsl:
            tags.append("WSL")
        if self.is_container:
            tags.append("container")
        suffix = f"  [{', '.join(tags)}]" if tags else ""
        return f"{name} ({arch}){suffix}"

    def _cgroup_has(self, *terms: str) -> bool:
        try:
            content = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="ignore").lower()
            return any(t in content for t in terms)
        except OSError:
            return False
