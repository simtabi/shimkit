"""shimkit core primitives — shared between every tool.

Every tool builds on these:
    CommandResult/CommandRunner — single chokepoint for subprocess execution
    Platform                    — OS/arch/container/WSL detection
    Shell, ShellConfigWriter    — shell detection + idempotent rc-file writes
    UI                          — coloured terminal output, NO_COLOR-aware
    Menu                        — questionary wrapper with fallback
"""

from .command import CommandResult, CommandRunner, has_sudo_cached, is_root, sudo_prefix
from .json_event import Event, emit_json
from .log import attach_file_handler, get_logger, set_verbose
from .menu import AskResult, FallbackMenu, Menu
from .pkgmgr import PackageManager
from .platform import Platform
from .shell import Shell, ShellConfigWriter, java_home_for
from .systemd import Systemd, UnitState
from .ui import UI

__all__ = [
    "UI",
    "AskResult",
    "CommandResult",
    "CommandRunner",
    "Event",
    "FallbackMenu",
    "Menu",
    "PackageManager",
    "Platform",
    "Shell",
    "ShellConfigWriter",
    "Systemd",
    "UnitState",
    "attach_file_handler",
    "emit_json",
    "get_logger",
    "has_sudo_cached",
    "is_root",
    "java_home_for",
    "set_verbose",
    "sudo_prefix",
]
