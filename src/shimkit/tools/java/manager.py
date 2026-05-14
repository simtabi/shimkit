"""Top-level orchestrator for the Java tool.

Builder pattern: ``JavaManager.create().boot().run()``. ``boot()`` wires
all components and returns self; ``run()`` drives the interactive menu.
Direct subcommand invocations (``shimkit java install 21``) call the
non-interactive methods (``install``, ``list_installations``, …) instead
of running the menu.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Callable

from shimkit import __version__
from shimkit.config import get_config
from shimkit.core import (
    UI,
    Menu,
    Platform,
    Shell,
    java_home_for,
)

from .brew import Brew
from .installer import JavaInstaller
from .models import JavaInstallation, JavaVersion
from .oracle import OracleRemover
from .scanner import JavaScanner


class JavaManager:
    """Wires components and runs either the interactive menu or direct commands."""

    def __init__(self) -> None:
        self._platform: Platform | None = None
        self._shell: Shell | None = None
        self._brew: Brew | None = None
        self._scanner: JavaScanner | None = None
        self._installer: JavaInstaller | None = None
        self._remover: OracleRemover | None = None

    @classmethod
    def create(cls) -> JavaManager:
        return cls()

    def boot(self) -> JavaManager:
        """Detect platform/shell, wire components. Exits on unsupported OS."""
        self._platform = Platform.detect()
        if not self._platform.is_supported:
            UI.error(
                f"Unsupported platform: {self._platform.system}. "
                "macOS and Linux (including WSL and containers) are supported."
            )
            sys.exit(1)
        self._shell = Shell.detect(self._platform).ensure_config_exists()
        self._brew = Brew(self._platform)
        self._scanner = JavaScanner(self._platform, self._brew)
        self._installer = JavaInstaller(self._platform, self._brew, self._shell)
        self._remover = OracleRemover(self._platform)
        return self

    # --- public non-interactive surface ------------------------------------
    # Used by `shimkit java <subcommand>` — does not show the menu.

    def install(self, version: str) -> bool:
        assert self._installer and self._brew and self._shell
        if not self._brew.installed:
            UI.warning("Homebrew not found — installing now…")
            if not self._brew.install_self():
                UI.error("Homebrew installation failed.")
                return False
        UI.header(f"Installing OpenJDK {version}")
        if not self._installer.install(version):
            UI.error(f"Installation of OpenJDK {version} failed.")
            return False
        UI.success(f"OpenJDK {version} installed!")
        self._installer.reload_env()
        if not self._installer.verify():
            UI.warning(
                "Verification failed — restart your terminal or run: "
                f"source {self._shell.config_file}"
            )
        return True

    def uninstall(self, version: str) -> bool:
        assert self._installer
        UI.header(f"Uninstalling openjdk@{version}")
        if not self._installer.uninstall(version):
            UI.error(f"Failed to uninstall openjdk@{version}.")
            return False
        UI.success(f"openjdk@{version} uninstalled.")
        self._installer.reload_env()
        if f"openjdk@{version}" in os.environ.get("JAVA_HOME", ""):
            os.environ.pop("JAVA_HOME", None)
        return True

    def upgrade(self, version: str | None = None) -> bool:
        """Upgrade one version, or every outdated brew openjdk if version is None."""
        assert self._installer and self._brew and self._scanner
        if version is not None:
            return self._installer.upgrade(version)
        ok = True
        for pkg in self._brew.outdated_java():
            name = pkg.get("name", "")
            if "@" in name:
                v = name.split("@")[1]
                if not self._installer.upgrade(v):
                    ok = False
        return ok

    def switch_active(self, to_version: str) -> bool:
        assert self._installer and self._brew and self._platform
        if not self._installer.switch(to_version):
            return False
        self._installer.reload_env()
        os.environ["JAVA_HOME"] = java_home_for(
            self._brew.prefix, to_version, self._platform.is_macos
        )
        return True

    def list_installations(self) -> list[JavaInstallation]:
        assert self._scanner
        return self._scanner.scan()

    def remove_oracle(self) -> bool:
        assert self._remover
        if not self._remover.available():
            UI.info("Oracle Java removal is macOS only.")
            return False
        return self._remover.remove()

    # --- interactive menu --------------------------------------------------

    def check_self_update(self) -> JavaManager:
        """Check for a shimkit upgrade and offer to apply it.

        Delegates to ``shimkit.self_update``: queries PyPI for the latest
        version and dispatches via uv/pipx/brew/pip if newer. Silent on
        network failure.
        """
        if not get_config().self_update.check_on_startup:
            return self
        from shimkit import self_update as _su

        with UI.spinner("Checking for shimkit updates"):
            res = _su.check()
        if not res.has_update or res.method is None:
            return self
        UI.warning(f"shimkit update available: {res.current} → {res.latest}")
        if Menu.confirm(f"Upgrade shimkit via {res.method}?"):
            if _su.apply(res.method):
                UI.success(f"shimkit upgraded to {res.latest}! Restarting…")
                os.execv(sys.executable, [sys.executable, *sys.argv])
            else:
                UI.error("Upgrade failed — continuing with current version")
        return self

    def check_java_updates(self) -> JavaManager:
        assert self._brew and self._installer
        if not self._brew.installed:
            return self
        with UI.spinner("Checking for Java updates"):
            outdated = self._brew.outdated_java()
        if not outdated:
            return self
        UI.warning("Java updates available:")
        for pkg in outdated:
            iv = pkg.get("installed_versions") or ["?"]
            installed = iv[0] if iv else "?"
            latest = pkg.get("current_version", "?")
            UI.info(f"  {pkg['name']}  ({installed} → {latest})")
        if Menu.confirm("Upgrade now?"):
            for pkg in outdated:
                name = pkg.get("name", "")
                if "@" not in name:
                    continue
                v = name.split("@")[1]
                if v:
                    UI.info(f"Upgrading {pkg['name']}…")
                    if self._installer.upgrade(v):
                        UI.success(f"{pkg['name']} upgraded!")
                    else:
                        UI.error(f"Failed to upgrade {pkg['name']}")
        return self

    def run(self) -> None:
        """Display the status banner and enter the menu loop."""
        assert self._scanner and self._platform and self._shell
        with UI.spinner("Detecting Java installation"):
            java_info = self._scanner.active_version_string.splitlines()[0] or "Not installed"
        self._print_banner(java_info)
        self.check_self_update()
        self.check_java_updates()

        menu_items: list[tuple[str, Callable[[], None]]] = [
            ("Install Java", self._menu_install),
            ("List installed versions", self._menu_list),
            ("Switch active version", self._menu_switch),
            ("Upgrade existing Java", self._menu_upgrade),
            ("Uninstall Java", self._menu_uninstall),
            ("Remove Oracle Java", self._menu_remove_oracle),
            ("Exit", lambda: None),
        ]
        labels = [lbl for lbl, _ in menu_items]
        dispatch = dict(menu_items)

        while True:
            choice = Menu.select("What would you like to do?", labels)
            if choice is None or choice == "Exit":
                UI.info("Goodbye!")
                break
            handler = dispatch.get(choice)
            if handler:
                handler()

    # --- banner ------------------------------------------------------------

    def _print_banner(self, java_info: str) -> None:
        """Print the boxed startup banner using the generic UI.banner."""
        assert self._platform and self._shell
        UI.banner(
            title_left="[~]  shimkit · Java",
            title_right=f"v{__version__}",
            sections=[
                [
                    ("Version", f"v{__version__}"),
                    ("Platform", self._platform.description),
                    ("Shell", self._shell.description),
                    ("Java", java_info),
                ],
            ],
        )

    # --- legacy interactive menu actions -----------------------------------

    def _menu_install(self) -> None:
        assert self._installer and self._scanner and self._brew and self._shell
        back = get_config().ui.back_label
        installed = set(self._scanner.homebrew_java_versions())
        versions = JavaVersion.all()

        choices = [f"{v}  [✓ installed]" if v.number in installed else str(v) for v in versions] + [
            back
        ]
        picked = Menu.select("Select Java version to install:", choices)
        if not picked or picked == back:
            return
        version = picked.split()[1]

        if version in installed:
            UI.info(f"OpenJDK {version} is already installed.")
            if not Menu.confirm(f"Re-install OpenJDK {version}?", default=False):
                return
            UI.header(f"Re-installing OpenJDK {version}")
            ok = self._installer.reinstall(version)
        else:
            if not Menu.confirm(f"Install OpenJDK {version}?"):
                return
            UI.header(f"Installing OpenJDK {version}")
            if not self._brew.installed:
                UI.warning("Homebrew not found — installing now…")
                if not self._brew.install_self():
                    UI.error("Homebrew installation failed.")
                    return
            ok = self._installer.install(version)

        if ok:
            UI.success(f"OpenJDK {version} ready!")
            self._installer.reload_env()
            if not self._installer.verify():
                UI.warning(
                    "Verification failed — restart your terminal or run: "
                    f"source {self._shell.config_file}"
                )
        else:
            UI.error(f"Operation on OpenJDK {version} failed.")

    def _menu_upgrade(self) -> None:
        assert self._scanner and self._brew and self._installer
        back = get_config().ui.back_label
        installed = self._scanner.homebrew_java_versions()
        if not installed:
            UI.info("No Homebrew Java installations found.")
            return
        outdated_names = {p.get("name", "") for p in self._brew.outdated_java()}
        choices: list[str] = []
        for v in installed:
            tag = "⚠ update available" if f"openjdk@{v}" in outdated_names else "✓ up to date"
            choices.append(f"openjdk@{v}  {tag}")
        choices.append(back)
        if not any("⚠" in c for c in choices):
            UI.success("All Java installations are up to date.")
            return
        selected = Menu.checkbox("Select versions to upgrade:", choices)
        if not selected or selected == [back]:
            return
        for label in (s for s in selected if s != back):
            v = label.split("@")[1].split()[0]
            UI.info(f"Upgrading openjdk@{v}…")
            if self._installer.upgrade(v):
                UI.success(f"openjdk@{v} upgraded!")
            else:
                UI.error(f"Failed to upgrade openjdk@{v}")

    def _menu_switch(self) -> None:
        assert self._scanner and self._installer and self._brew and self._platform
        back = get_config().ui.back_label
        installed = self._scanner.homebrew_java_versions()
        if not installed:
            UI.info("No Java installations found.")
            return
        if len(installed) == 1:
            UI.info("Only one Java version installed — nothing to switch.")
            return
        choices = [f"openjdk@{v}" for v in installed] + [back]
        picked = Menu.select("Select version to make active:", choices)
        if not picked or picked == back:
            return
        version = picked.replace("openjdk@", "")
        if Menu.confirm(f"Switch active Java to {picked}?"):
            if self.switch_active(version):
                UI.success(f"Switched to {picked}!")
            else:
                UI.error("Switch failed.")

    def _menu_list(self) -> None:
        UI.header("Installed Java Versions")
        installs = self.list_installations()
        if not installs:
            UI.info("No Java installations found.")
        else:
            for inst in installs:
                tick = "✓" if inst.active else " "
                UI.info(f"  {tick} [{inst.kind}] {inst.version}")
                UI.dim(f"      {inst.path}")
        UI.line()
        assert self._scanner
        active = self._scanner.active_version_string
        if active and active != "Not installed":
            UI.info(f"Active: {active.splitlines()[0]}")
        with contextlib.suppress(EOFError):
            input("\nPress Enter to return to menu…")

    def _menu_remove_oracle(self) -> None:
        assert self._remover and self._scanner
        if not self._remover.available():
            UI.info("Oracle Java removal is macOS only.")
            return
        installs = self._scanner.scan()
        oracle = [i for i in installs if i.kind == "Oracle"]
        if not oracle:
            UI.info("No Oracle Java installations found.")
            return
        UI.warning(f"Found {len(oracle)} Oracle Java installation(s):")
        for o in oracle:
            UI.info(f"  {o.version}  at  {o.path}")
        if Menu.confirm("Remove Oracle Java? (cannot be undone)", default=False):
            UI.header("Removing Oracle Java")
            if self._remover.remove():
                UI.success("Oracle Java removed.")
            else:
                UI.warning("Nothing was removed — you may need to run with sudo.")

    def _menu_uninstall(self) -> None:
        assert self._scanner and self._installer and self._shell
        back = get_config().ui.back_label
        installed = self._scanner.homebrew_java_versions()
        if not installed:
            UI.info("No Homebrew Java installations found.")
            return
        choices = [f"openjdk@{v}" for v in installed] + [back]
        picked = Menu.select("Select version to uninstall:", choices)
        if not picked or picked == back:
            return
        version = picked.replace("openjdk@", "")
        if not Menu.confirm(f"Uninstall {picked}? This cannot be undone.", default=False):
            return
        if self.uninstall(version):
            UI.info(
                "Shell config entry removed. Restart your terminal or run: "
                f"source {self._shell.config_file}"
            )
