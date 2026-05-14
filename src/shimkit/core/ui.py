"""Terminal UI primitives.

Colour decisions read from config: ``config.ui.color`` is one of
``auto`` (default — colour when stdout is a TTY and NO_COLOR is unset),
``always``, or ``never``. The loader already maps the NO_COLOR env var
to ``never`` before validation, so this module just trusts the resolved
value.
"""

from __future__ import annotations

import itertools
import re
import sys
import threading
import time
from collections.abc import Iterator

from shimkit.config import get_config

_ANSI_RE = re.compile(r"\033\[[^m]*m")


class UI:
    """Single source of truth for terminal output.

    Every method is a classmethod that prints and returns ``cls`` so chains
    like ``UI.header("Title").success("Done")`` work. ANSI codes are
    stripped automatically when colour is disabled.

    ``set_quiet(True)`` suppresses non-error output. ``error()`` always
    prints regardless so failures aren't silenced.
    """

    _H = "\033[95m"
    _B = "\033[94m"
    _C = "\033[96m"
    _G = "\033[92m"
    _Y = "\033[93m"
    _R = "\033[91m"
    _RST = "\033[0m"
    _BOLD = "\033[1m"
    _DIM = "\033[2m"

    _quiet: bool = False
    _color_override: str | None = None
    _no_input: bool = False

    @classmethod
    def set_quiet(cls, quiet: bool) -> None:
        """Suppress all non-error output until called again with False."""
        cls._quiet = quiet

    @classmethod
    def set_color_mode(cls, mode: str | None) -> None:
        """Override the config-driven colour mode.

        ``mode`` is ``"auto"``, ``"always"``, ``"never"``, or ``None``
        to drop back to whatever ``config.ui.color`` says. Used by the
        shared ``--color=auto|always|never`` and ``--no-color`` flags.
        """
        cls._color_override = mode

    @classmethod
    def set_no_input(cls, no_input: bool) -> None:
        """Mark the session as non-interactive.

        Tools that would otherwise prompt should check ``UI.is_no_input()``
        before calling into ``Menu``. Stays set until cleared by tests
        via ``set_no_input(False)``.
        """
        cls._no_input = no_input

    @classmethod
    def is_no_input(cls) -> bool:
        return cls._no_input

    @classmethod
    def _color_enabled(cls) -> bool:
        mode: str | None = cls._color_override
        if mode is None:
            # UI must keep working even when the config itself is invalid,
            # otherwise `shimkit config validate` would crash on the very
            # error message that explains the problem. Fall back to auto.
            try:
                mode = get_config().ui.color
            except Exception:
                mode = "auto"
        if mode == "always":
            return True
        if mode == "never":
            return False
        return sys.stdout.isatty()

    @classmethod
    def _emit(cls, text: str, *, force: bool = False) -> None:
        if cls._quiet and not force:
            return
        print(text if cls._color_enabled() else _ANSI_RE.sub("", text))

    @classmethod
    def header(cls, msg: str) -> type[UI]:
        cls._emit(f"\n{cls._H}{cls._BOLD}{msg}{cls._RST}\n")
        return cls

    @classmethod
    def success(cls, msg: str) -> type[UI]:
        cls._emit(f"{cls._G}✓ {msg}{cls._RST}")
        return cls

    @classmethod
    def error(cls, msg: str) -> type[UI]:
        # Errors always print, even in quiet mode.
        cls._emit(f"{cls._R}✗ {msg}{cls._RST}", force=True)
        return cls

    @classmethod
    def warning(cls, msg: str) -> type[UI]:
        cls._emit(f"{cls._Y}⚠ {msg}{cls._RST}")
        return cls

    @classmethod
    def info(cls, msg: str) -> type[UI]:
        cls._emit(f"{cls._C}ℹ {msg}{cls._RST}")  # noqa: RUF001 — intentional info glyph
        return cls

    @classmethod
    def dim(cls, msg: str) -> type[UI]:
        cls._emit(f"{cls._DIM}{msg}{cls._RST}")
        return cls

    @classmethod
    def line(cls, msg: str = "") -> type[UI]:
        """Emit a plain line with no glyph, indent, or colour.

        Use for factual output (``doctor``, ``config show``, ``version``)
        where the caller wants the string verbatim. The single UI chokepoint
        for what would otherwise be ``print()`` or ``typer.echo()``.
        """
        cls._emit(msg)
        return cls

    @classmethod
    def spinner(cls, message: str) -> _SpinnerCtx:
        return _SpinnerCtx(message, color_enabled=cls._color_enabled())

    @classmethod
    def banner(
        cls,
        title_left: str,
        title_right: str,
        sections: list[list[tuple[str, str]]],
        min_width: int = 60,
    ) -> type[UI]:
        """Print a boxed status banner — generic replacement for the old
        Java-specific ``UI.status_header``.

        ``sections`` is a list of row groups; each group is a list of
        ``(label, value)`` tuples. Sections are separated by mid-bars.
        Labels are auto-aligned to the widest label across all sections.
        """

        def vlen(s: str) -> int:
            return len(_ANSI_RE.sub("", s))

        def rpad(s: str, w: int) -> str:
            return s + " " * max(0, w - vlen(s))

        all_rows = [r for sec in sections for r in sec]
        if not all_rows:
            return cls

        label_w = max(vlen(lbl) for lbl, _ in all_rows)
        title_min = vlen(title_left) + vlen(title_right) + 8
        # row width: "| " + label + " | " + value + " |"
        content_min = max(vlen(v) + label_w + 7 for _, v in all_rows)
        width = max(min_width, content_min, title_min)
        value_w = width - label_w - 7

        bd = cls._H + cls._BOLD
        rst = cls._RST

        top = f"{bd}+{'-' * (width - 2)}+{rst}"
        mid = f"{bd}+{'-' * (label_w + 2)}+{'-' * (value_w + 2)}+{rst}"
        title_pad = (width - 2) - 2 - vlen(title_left) - vlen(title_right) - 2

        def fmt_row(label: str, value: str) -> str:
            return (
                f"{bd}|{rst} {cls._BOLD}{rpad(label, label_w)}{rst} "
                f"{bd}|{rst} {rpad(value, value_w)} {bd}|{rst}"
            )

        cls._emit("")
        cls._emit(top)
        cls._emit(
            f"{bd}|{rst}"
            f"  {bd}{title_left}{rst}"
            f"{' ' * max(1, title_pad)}"
            f"{cls._DIM}{title_right}{rst}"
            f"  {bd}|{rst}"
        )
        cls._emit(mid)
        for i, sec in enumerate(sections):
            for lbl, val in sec:
                cls._emit(fmt_row(lbl, val))
            if i < len(sections) - 1:
                cls._emit(mid)
        cls._emit(mid)
        cls._emit("")
        return cls


class _SpinnerCtx:
    """Context manager that runs an ASCII spinner in a daemon thread."""

    _FRAMES: tuple[str, ...] = ("[|]", "[/]", "[-]", "[\\]")

    def __init__(self, message: str, color_enabled: bool) -> None:
        self._message = message
        self._color = color_enabled
        self._is_tty = sys.stdout.isatty()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> _SpinnerCtx:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join()

    def _run(self) -> None:
        blank = "\r" + " " * (len(self._message) + 14) + "\r"
        if self._is_tty:
            sys.stdout.write("\033[?25l")  # hide cursor
            sys.stdout.flush()
        frames: Iterator[str] = itertools.cycle(self._FRAMES)
        for f in frames:
            if self._stop.is_set():
                break
            line = (
                f"\r  {UI._DIM}{f}{UI._RST}  {self._message}  "
                if self._color
                else f"\r  {f}  {self._message}  "
            )
            sys.stdout.write(line)
            sys.stdout.flush()
            time.sleep(0.1)
        sys.stdout.write(blank)
        if self._is_tty:
            sys.stdout.write("\033[?25h")  # show cursor
        sys.stdout.flush()
