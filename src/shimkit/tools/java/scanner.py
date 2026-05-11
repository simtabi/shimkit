"""Multi-source Java installation scanner.

Search paths are read from ``config.tools.java.scan_paths`` keyed by OS
(``macos`` / ``linux`` / ``container``). Discoveries are deduplicated by
resolved real-path so a single installation reported by multiple sources
appears only once.
"""

from __future__ import annotations

import os
from pathlib import Path

from shimkit.config import get_config
from shimkit.core import CommandRunner, Platform

from .brew import Brew
from .models import JavaInstallation


class JavaScanner:
    """Discover Java installations across system, brew, container, and SDKman paths."""

    def __init__(self, platform: Platform, brew: Brew) -> None:
        self._platform = platform
        self._brew = brew

    def scan(self) -> list[JavaInstallation]:
        """Return all discovered installations, deduplicated by real path."""
        seen: set[str] = set()
        results: list[JavaInstallation] = []
        active_raw = self._active_version_raw().lower()
        cfg_paths = get_config().tools.java.scan_paths

        def add(kind: str, name: str, path: Path) -> None:
            try:
                real = str(path.resolve())
            except OSError:
                real = str(path)
            if real in seen:
                return
            seen.add(real)
            tokens = [t for t in (name.lower(), real.lower()) if t]
            active = any(tok in active_raw for tok in tokens)
            results.append(JavaInstallation(kind, name, str(path), active))

        # System JVM directories (OS-specific)
        os_paths = cfg_paths.macos if self._platform.is_macos else cfg_paths.linux
        for raw_path in os_paths:
            jvm_base = Path(raw_path).expanduser()
            if not jvm_base.exists():
                continue
            # Heuristics differ by directory shape:
            for entry in jvm_base.iterdir():
                if entry.name.startswith("openjdk"):
                    add("Homebrew", entry.name, entry)
                elif jvm_base.name in ("JavaVirtualMachines", "jvm", "jdk"):
                    kind = (
                        "Oracle"
                        if "jdk" in entry.name.lower() and "openjdk" not in entry.name.lower()
                        else "Homebrew"
                    )
                    add(kind, entry.name, entry)

        # Container/CI image paths
        for raw_path in cfg_paths.container:
            base = Path(raw_path).expanduser()
            if base.is_dir():
                for entry in base.iterdir():
                    if entry.is_dir():
                        add("System", entry.name, entry)

        # SDKman ~/.sdkman/candidates/java/<version>
        sdkman_java = Path.home() / ".sdkman" / "candidates" / "java"
        if sdkman_java.exists():
            for entry in sdkman_java.iterdir():
                if entry.is_dir() and entry.name != "current":
                    add("SDKman", entry.name, entry)

        # JAVA_HOME env var
        java_home_env = os.environ.get("JAVA_HOME", "")
        if java_home_env:
            p = Path(java_home_env)
            if p.is_dir():
                add("JAVA_HOME", p.name or java_home_env, p)

        sdkman_current = sdkman_java / "current"
        if sdkman_current.is_symlink():
            add("SDKman", "current", sdkman_current)

        return results

    def homebrew_java_versions(self) -> list[str]:
        """Return brew openjdk versions installed under brew prefix, newest first."""
        versions: list[str] = []
        opt_dir = Path(self._brew.prefix) / "opt"
        if opt_dir.exists():
            for p in opt_dir.glob("openjdk*"):
                if "@" in p.name:
                    versions.append(p.name.split("@")[1])
        return sorted(set(versions), key=lambda x: int(x) if x.isdigit() else 0, reverse=True)

    def _active_version_raw(self) -> str:
        r = CommandRunner.run(["java", "-version"])
        if not r.ok and not r.stderr:
            return ""
        raw = (r.stderr or r.stdout).strip()
        if not r.ok and any(
            kw in raw.lower() for kw in ("not found", "no such file", "cannot find")
        ):
            return ""
        return raw

    @property
    def active_version_string(self) -> str:
        raw = self._active_version_raw()
        return raw if raw else "Not installed"
