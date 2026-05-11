"""Install / reinstall / uninstall / upgrade / switch Java via Homebrew."""

from __future__ import annotations

import os

from shimkit.core import (
    UI,
    CommandRunner,
    Platform,
    Shell,
    ShellConfigWriter,
    sudo_prefix,
)

from .brew import Brew


class JavaInstaller:
    """Coordinates Brew, ShellConfigWriter, and Platform for OpenJDK lifecycle."""

    def __init__(self, platform: Platform, brew: Brew, shell: Shell) -> None:
        self._platform = platform
        self._brew = brew
        self._shell = shell

    def install(self, version: str) -> bool:
        with UI.spinner("Updating Homebrew…"):
            self._brew.update()
        r = self._brew.install_pkg(f"openjdk@{version}")
        if not r.ok:
            return False
        self._link(version)
        self._write_env(version)
        return True

    def reinstall(self, version: str) -> bool:
        r = self._brew.reinstall_pkg(f"openjdk@{version}")
        if not r.ok:
            return False
        self._link(version)
        self._write_env(version)
        return True

    def uninstall(self, version: str) -> bool:
        self._unlink(version)
        r = self._brew.uninstall_pkg(f"openjdk@{version}")
        if not r.ok:
            return False
        ShellConfigWriter.for_shell(self._shell).remove_java_env(version)
        return True

    def upgrade(self, version: str) -> bool:
        r = self._brew.upgrade_pkg(f"openjdk@{version}")
        if not r.ok:
            return False
        self._link(version)
        return True

    def switch(self, to_version: str) -> bool:
        return self._brew.link(f"openjdk@{to_version}", force=True).ok

    def verify(self) -> bool:
        return CommandRunner.run(["java", "-version"]).returncode == 0

    def reload_env(self) -> bool:
        env = self._shell.source()
        if env:
            os.environ.update(env)
            return True
        return False

    # --- macOS-only helpers -------------------------------------------------

    def _unlink(self, version: str) -> None:
        if not self._platform.is_macos:
            return
        target = self._platform.jvm_base / f"openjdk-{version}.jdk"
        if not target.exists() and not target.is_symlink():
            return
        prefix = sudo_prefix()
        if not prefix and os.geteuid() != 0:
            return
        CommandRunner.run([*prefix, "rm", "-f", str(target)])

    def _link(self, version: str) -> None:
        if not self._platform.is_macos:
            return
        prefix = sudo_prefix()
        if not prefix and os.geteuid() != 0:
            return
        jdk_src = f"{self._brew.prefix}/opt/openjdk@{version}/libexec/openjdk.jdk"
        target = str(self._platform.jvm_base / f"openjdk-{version}.jdk")
        CommandRunner.run([*prefix, "mkdir", "-p", str(self._platform.jvm_base)])
        CommandRunner.run([*prefix, "ln", "-sfn", jdk_src, target])

    def _write_env(self, version: str) -> None:
        ShellConfigWriter.for_shell(self._shell).write_java_env(
            self._brew.prefix, version, self._platform
        )
