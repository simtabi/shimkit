"""End-to-end tests for the deprecation shim at repo root.

The shim file ``java_update_manager.py`` keeps existing user aliases
working through the v2.x cycle. These tests verify it still forwards
correctly so a future cli.py refactor can't break the contract
invisibly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHIM = ROOT / "java_update_manager.py"


def test_shim_exists() -> None:
    assert SHIM.exists(), "java_update_manager.py shim missing from repo root"


def test_shim_help_forwards_to_shimkit_java() -> None:
    """`python java_update_manager.py --help` should print the shimkit java help
    and a deprecation notice on stderr."""
    result = subprocess.run(
        [sys.executable, str(SHIM), "--help"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, f"shim exited {result.returncode}; stderr={result.stderr}"
    # Deprecation notice on stderr
    assert "deprecated" in result.stderr.lower()
    assert "shimkit java" in result.stderr
    # Forwarded help on stdout
    assert "Manage OpenJDK installations" in result.stdout


def test_shim_install_subcommand_forwards() -> None:
    """`python java_update_manager.py install --help` reaches `shimkit java install`."""
    result = subprocess.run(
        [sys.executable, str(SHIM), "install", "--help"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0
    assert "Major version" in result.stdout
