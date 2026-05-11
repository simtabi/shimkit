"""shimkit core primitives — shared between every tool.

Every tool builds on these:
    CommandResult/CommandRunner — single chokepoint for subprocess execution
    Platform                    — OS/arch/container/WSL detection
    Shell, ShellConfigWriter    — shell detection + idempotent rc-file writes
    UI                          — coloured terminal output, NO_COLOR-aware
    Menu                        — questionary wrapper with fallback
"""

from .command import CommandResult, CommandRunner, sudo_prefix
from .menu import AskResult, FallbackMenu, Menu
from .pkgmgr import PackageManager
from .platform import Platform
from .shell import Shell, ShellConfigWriter, java_home_for
from .ui import UI

__all__ = [
    "UI",
    "AskResult",
    "CommandResult",
    "CommandRunner",
    "FallbackMenu",
    "Menu",
    "PackageManager",
    "Platform",
    "Shell",
    "ShellConfigWriter",
    "java_home_for",
    "sudo_prefix",
]
