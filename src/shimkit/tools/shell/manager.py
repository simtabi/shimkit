"""Top-level orchestrator for the shell upgrader.

Mirrors JavaManager's shape: ``ShellManager.create().boot().run()`` for
the interactive menu; non-interactive methods (``info``, ``upgrade_shell``,
``simulate``) for the Typer subcommands.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from shimkit.config import get_config
from shimkit.core import UI, Menu, PackageManager, Platform, Shell

from .upgrader import ShellUpgrader


class ShellManager:
    def __init__(self) -> None:
        self._platform: Platform | None = None
        self._pkgmgr: PackageManager | None = None
        self._upgrader: ShellUpgrader | None = None

    @classmethod
    def create(cls) -> ShellManager:
        return cls()

    def boot(self) -> ShellManager:
        self._platform = Platform.detect()
        if not self._platform.is_supported:
            UI.error(
                f"Unsupported platform: {self._platform.system}. "
                "macOS and Linux are supported."
            )
            sys.exit(1)
        self._pkgmgr = PackageManager.detect(self._platform)
        if self._pkgmgr is None:
            UI.error(
                "No supported package manager found. Configure one in "
                "config.package_managers.preference_order or install brew/apt/dnf/etc."
            )
            sys.exit(1)
        self._upgrader = ShellUpgrader(self._platform, self._pkgmgr)
        return self

    # --- non-interactive surface -------------------------------------------

    def info(self) -> None:
        assert self._platform and self._pkgmgr and self._upgrader
        active = Shell.detect(self._platform)
        UI.header("Shell Info")
        UI.info(f"  Platform        {self._platform.description}")
        UI.info(f"  Active shell    {active.description}")
        UI.info(f"  Package mgr     {self._pkgmgr.name}")
        UI.info("")
        UI.info("  Installed shells:")
        for name in self._upgrader.supported_shells:
            v = self._upgrader.installed_version(name) or "not installed"
            UI.info(f"    {name:7s}  {v}")

    def upgrade_shell(self, name: str, force: bool = False) -> bool:
        """Upgrade ``name``. Prompts when targeting the active shell unless ``force``."""
        assert self._upgrader and self._platform
        if name not in self._upgrader.supported_shells:
            UI.error(
                f"{name!r} is not in supported_shells "
                f"({', '.join(self._upgrader.supported_shells)})."
            )
            return False
        active = Shell.detect(self._platform).name
        if active == name and not force:
            UI.warning(
                f"{name} is your currently active shell. Upgrading it mid-session "
                "can leave you with broken builtins until you start a new terminal."
            )
            if not Menu.confirm(
                f"Continue upgrading {name} anyway?", default=False
            ):
                UI.info("Cancelled.")
                return False
        UI.header(f"Upgrading {name}")
        if self._upgrader.upgrade(name):
            UI.success(f"{name} upgraded.")
            return True
        UI.error(f"Failed to upgrade {name}.")
        return False

    def simulate(self, name: str) -> None:
        assert self._upgrader
        UI.header(f"Simulate: upgrade {name}")
        UI.dim(self._upgrader.simulate(name))

    # --- interactive menu --------------------------------------------------

    def run(self) -> None:
        assert self._upgrader
        actions: list[tuple[str, Callable[[], None]]] = [
            ("Show shell info", self.info),
            ("Upgrade a shell", self._menu_upgrade),
            ("Simulate an upgrade", self._menu_simulate),
            ("Exit", lambda: None),
        ]
        labels = [lbl for lbl, _ in actions]
        dispatch = dict(actions)

        while True:
            choice = Menu.select("Shell upgrader — what would you like to do?", labels)
            if choice is None or choice == "Exit":
                UI.info("Goodbye!")
                break
            handler = dispatch.get(choice)
            if handler:
                handler()

    def _menu_upgrade(self) -> None:
        assert self._upgrader
        back = get_config().ui.back_label
        choices = [*self._upgrader.supported_shells, back]
        picked = Menu.select("Pick a shell to upgrade:", choices)
        if not picked or picked == back:
            return
        if Menu.confirm(f"Upgrade {picked} via the host package manager?", default=False):
            self.upgrade_shell(picked)

    def _menu_simulate(self) -> None:
        assert self._upgrader
        back = get_config().ui.back_label
        choices = [*self._upgrader.supported_shells, back]
        picked = Menu.select("Pick a shell to simulate:", choices)
        if not picked or picked == back:
            return
        self.simulate(picked)
