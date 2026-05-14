"""Active-shell detection and idempotent rc-file writes.

Shell.CONFIG_MAP used to be a class-level constant; it now reads from the
config layer (``config.tools.shell.config_map``) so users can register
new shells without touching code. The marker comment template
(``# java-manager:openjdk@<v>``) intentionally stays as a code constant —
changing it breaks idempotent re-writes, so it is not user-configurable.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from shimkit.config import get_config

from .command import CommandRunner
from .platform import Platform


class Shell:
    """Detected shell for the current process."""

    def __init__(self, name: str, binary: str, config_file: Path) -> None:
        self.name = name
        self.binary = binary
        self.config_file = config_file

    @classmethod
    def detect(cls, platform: Platform) -> Shell:
        """Detect shell from $SHELL, mapping name → rc-file via config.

        If both ``rc_file`` and ``fallback_rc`` are configured, prefer the
        primary unless it's missing on disk while the fallback exists.
        Linux bash users typically have ``~/.bashrc`` rather than
        ``~/.bash_profile`` — the fallback handles this without forking.
        """
        shell_path = os.environ.get("SHELL", "")
        if not shell_path:
            shell_path = "/bin/zsh" if platform.is_macos else "/bin/bash"
        name = Path(shell_path).name
        rc_file = cls._rc_file_for(name)
        return cls(name, shell_path, Path.home() / rc_file)

    @staticmethod
    def _rc_file_for(name: str) -> str:
        cfg = get_config().tools.shell.config_map
        entry = cfg.get(name)
        if entry is None:
            return ".profile"
        primary = Path.home() / entry.rc_file
        if entry.fallback_rc and not primary.exists():
            fallback = Path.home() / entry.fallback_rc
            if fallback.exists():
                return entry.fallback_rc
        return entry.rc_file

    def ensure_config_exists(self) -> Shell:
        """Create the shell config file and parents. Returns self for chaining."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.touch(exist_ok=True)
        return self

    def source(self) -> dict[str, str]:
        """Source the rc file and return the resulting environment.

        Fish is skipped — its syntax is incompatible with POSIX source.
        """
        if self.name == "fish":
            return {}
        if not self.config_file.exists():
            return {}
        quoted = shlex.quote(str(self.config_file))
        # shell=True needed: `source` is a shell builtin, not a binary.
        # The rc-file path is shlex.quote-escaped above so user input
        # cannot inject metacharacters.
        r = CommandRunner.run(
            f"source {quoted} && env",
            shell=True,  # nosec B604
            executable=self.binary,
        )
        env: dict[str, str] = {}
        if r.ok:
            for line in r.stdout.split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    env[k] = v
        return env

    @property
    def description(self) -> str:
        return f"{self.name}  →  {self.config_file}"


def java_home_for(brew_prefix: str, version: str, is_macos: bool) -> str:
    """Return the JAVA_HOME path for a Homebrew openjdk@<version> install.

    macOS includes the .jdk/Contents/Home suffix; Linux uses the bare opt path.
    Single source of truth for path layout — used by ShellConfigWriter and
    the Java tool's switch logic.
    """
    if is_macos:
        return f"{brew_prefix}/opt/openjdk@{version}/libexec/openjdk.jdk/Contents/Home"
    return f"{brew_prefix}/opt/openjdk@{version}"


class ShellConfigWriter:
    """Idempotent PATH and JAVA_HOME export-block writer.

    Each version's block is guarded by a marker comment, so calling
    write_java_env multiple times for the same version never duplicates
    exports. remove_java_env strips the marker plus the two export lines.
    """

    # Logic-critical: the marker template MUST stay code-local. Changing it
    # breaks idempotent re-writes for existing user rc files.
    _MARKER_TEMPLATE = "# java-manager:openjdk@{version}"

    def __init__(self, config_file: Path) -> None:
        self._file = config_file

    @classmethod
    def for_shell(cls, shell: Shell) -> ShellConfigWriter:
        return cls(shell.config_file)

    def write_java_env(
        self, brew_prefix: str, version: str, platform: Platform
    ) -> ShellConfigWriter:
        java_home = java_home_for(brew_prefix, version, platform.is_macos)
        marker = self._MARKER_TEMPLATE.format(version=version)
        block = (
            f"\n{marker}\n"
            f'export PATH="{brew_prefix}/opt/openjdk@{version}/bin:$PATH"\n'
            f'export JAVA_HOME="{java_home}"\n'
        )
        return self._append(block, marker)

    def remove_java_env(self, version: str) -> bool:
        marker = self._MARKER_TEMPLATE.format(version=version)
        if not self._has_marker(marker):
            return False
        try:
            lines = self._file.read_text(encoding="utf-8").splitlines(keepends=True)
            new_lines: list[str] = []
            skip = 0
            for line in lines:
                if skip > 0:
                    skip -= 1
                    continue
                if line.rstrip("\n") == marker:
                    skip = 2
                    if new_lines and new_lines[-1] == "\n":
                        new_lines.pop()
                    continue
                new_lines.append(line)
            self._file.write_text("".join(new_lines), encoding="utf-8")
            return True
        except OSError:
            return False

    def _has_marker(self, marker: str) -> bool:
        if not self._file.exists():
            return False
        try:
            return marker in self._file.read_text(encoding="utf-8")
        except OSError:
            return False

    def _append(self, block: str, marker: str) -> ShellConfigWriter:
        if not self._has_marker(marker):
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(block)
        return self
