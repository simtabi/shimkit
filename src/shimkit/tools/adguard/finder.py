"""Locate the AdGuard Home install and its YAML configuration.

Mirrors the ``find_agh_install`` shell function. Order:

1. Whatever ``systemctl cat AdGuardHome`` reports as ExecStart.
2. The config-driven candidate list.
"""

from __future__ import annotations

import re
from pathlib import Path

from shimkit.config import get_config
from shimkit.core import CommandRunner

from .models import AdGuardInstall

_EXEC_START_RE = re.compile(r"^ExecStart\s*=\s*[-@+!]*(\S+)", re.MULTILINE)

_YAML_CANDIDATES = (
    "AdGuardHome.yaml",
    "conf/AdGuardHome.yaml",
)


def _systemd_install_path() -> Path | None:
    r = CommandRunner.run(["systemctl", "cat", "AdGuardHome"])
    if not r.ok:
        return None
    m = _EXEC_START_RE.search(r.stdout)
    if not m:
        return None
    binary = Path(m.group(1))
    if not binary.is_file():
        return None
    return binary.parent


def detect(override: Path | None = None) -> AdGuardInstall | None:
    """Return the detected install, or None if AGH is not present."""
    roots: list[Path] = []
    if override:
        roots.append(Path(override))
    if (p := _systemd_install_path()):
        roots.append(p)
    for cand in get_config().tools.adguard.install_candidates:
        roots.append(Path(cand).expanduser())

    for root in roots:
        bin_path = root / "AdGuardHome"
        if bin_path.is_file():
            yaml_path: Path | None = None
            for rel in _YAML_CANDIDATES:
                p = root / rel
                if p.is_file():
                    yaml_path = p
                    break
            if yaml_path is None:
                for sys_path in ("/etc/AdGuardHome/AdGuardHome.yaml",
                                 "/var/lib/AdGuardHome/AdGuardHome.yaml"):
                    if Path(sys_path).is_file():
                        yaml_path = Path(sys_path)
                        break
            return AdGuardInstall(binary=bin_path, yaml_path=yaml_path, install_root=root)
    return None
