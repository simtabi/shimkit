#!/usr/bin/env python3
"""Backward-compatibility shim for users with `java_update_manager.py` aliased.

Forwards to ``shimkit java`` so the old invocation keeps working through
the v2.x cycle. Will be removed in v3.0.
"""

from __future__ import annotations

import sys


def _main() -> None:
    print(
        "[shimkit] java_update_manager.py is deprecated; use `shimkit java` instead.",
        file=sys.stderr,
    )
    from shimkit.cli import app

    # Forward all extra args to `shimkit java …`
    app(args=["java", *sys.argv[1:]], prog_name="shimkit")


if __name__ == "__main__":
    if sys.platform == "win32":
        print(
            "Windows is not directly supported.\n"
            "Please use Windows Subsystem for Linux (WSL).",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        _main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
