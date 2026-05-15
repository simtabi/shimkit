"""shimkit core primitives — shared between every tool.

Every tool builds on these:
    CommandResult/CommandRunner — single chokepoint for subprocess execution
    Platform                    — OS/arch/container/WSL detection
    Shell, ShellConfigWriter    — shell detection + idempotent rc-file writes
    UI                          — coloured terminal output, NO_COLOR-aware
    Menu                        — questionary wrapper with fallback
"""

from .command import CommandResult, CommandRunner, has_sudo_cached, is_root, sudo_prefix
from .docker import DockerEnv, DockerNotAvailableError, ExecOutcome
from .json_event import Event, emit_json
from .log import attach_file_handler, get_logger, set_verbose
from .menu import AskResult, FallbackMenu, Menu
from .pkgmgr import PackageManager
from .platform import Platform
from .shell import Shell, ShellConfigWriter, java_home_for
from .systemd import Systemd, UnitState
from .ui import UI
from .version import (
    Detector,
    Result,
    Status,
    ToolVersion,
    VersionConstraint,
    VersionViolationError,
)

__all__ = [
    "UI",
    "AskResult",
    "CommandResult",
    "CommandRunner",
    "Detector",
    "DockerEnv",
    "DockerNotAvailableError",
    "Event",
    "ExecOutcome",
    "FallbackMenu",
    "Menu",
    "PackageManager",
    "Platform",
    "Result",
    "Shell",
    "ShellConfigWriter",
    "Status",
    "Systemd",
    "ToolVersion",
    "UnitState",
    "VersionConstraint",
    "VersionViolationError",
    "attach_file_handler",
    "emit_json",
    "get_logger",
    "has_sudo_cached",
    "is_root",
    "java_home_for",
    "set_verbose",
    "sudo_prefix",
]
