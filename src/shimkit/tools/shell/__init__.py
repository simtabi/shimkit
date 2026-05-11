"""Shell upgrader — install/upgrade bash, zsh, fish, ksh via the host PM."""

from .manager import ShellManager
from .upgrader import ShellUpgrader

__all__ = ["ShellManager", "ShellUpgrader"]
