"""Interactive prompt wrapper around questionary, with a stdin fallback.

The legacy script lazily pip-installed questionary at startup. shimkit
declares it as a hard dependency and imports it normally. The fallback
remains for non-interactive contexts (no TTY, ``$TERM=dumb``, CI).
"""

from __future__ import annotations

import contextlib
import sys
from typing import Any

_q: Any
try:
    import questionary as _q
except ImportError:  # pragma: no cover — declared as a hard dep
    _q = None


class AskResult:
    """Adapter that gives FallbackMenu the same .ask() API as questionary widgets."""

    __slots__ = ("_value",)

    def __init__(self, value: Any) -> None:
        self._value = value

    def ask(self) -> Any:
        return self._value


class FallbackMenu:
    """Numbered stdin prompts. Used when questionary is unavailable or stdin is not a TTY."""

    def select(self, question: str, choices: list[str], **_: Any) -> AskResult:
        print(f"\n{question}")
        for i, c in enumerate(choices, 1):
            print(f"  {i:2}. {c}")
        try:
            raw = input("Enter number: ").strip()
            idx = int(raw) - 1
            result: str | None = choices[idx] if 0 <= idx < len(choices) else None
        except (ValueError, EOFError, IndexError):
            result = None
        return AskResult(result)

    def confirm(self, question: str, default: bool = True, **_: Any) -> AskResult:
        hint = "Y/n" if default else "y/N"
        try:
            raw = input(f"{question} ({hint}): ").strip().lower()
            result: bool | None = default if not raw else raw in ("y", "yes")
        except EOFError:
            result = default
        return AskResult(result)

    def checkbox(self, question: str, choices: list[str], **_: Any) -> AskResult:
        print(f"\n{question}")
        for i, c in enumerate(choices, 1):
            print(f"  {i:2}. {c}")
        print("  (comma-separated numbers, or Enter to select all)")
        try:
            raw = input("Select: ").strip()
            if not raw:
                result: list[str] | None = list(choices)
            else:
                indices = [int(x.strip()) - 1 for x in raw.split(",")]
                result = [choices[i] for i in indices if 0 <= i < len(choices)]
        except (ValueError, EOFError):
            result = []
        return AskResult(result)


class Menu:
    """questionary wrapper with safe defaults on cancel.

    Returns sane defaults (None / False / []) when prompts are cancelled or
    the backend is unavailable, so callers never need to guard against None.
    """

    _STYLE: Any = None

    @classmethod
    def _backend(cls) -> Any:
        if _q is None or not sys.stdin.isatty():
            return FallbackMenu()
        return _q

    @classmethod
    def _style(cls) -> Any:
        if _q is None:
            return None
        if cls._STYLE is None and hasattr(_q, "Style"):
            with contextlib.suppress(Exception):
                cls._STYLE = _q.Style(
                    [
                        ("selected", "fg:#00cc44 bold"),
                        ("pointer", "fg:#00cc44 bold"),
                        ("answer", "fg:#00cc44"),
                        ("question", "bold"),
                    ]
                )
        return cls._STYLE

    @classmethod
    def select(cls, question: str, choices: list[str]) -> str | None:
        backend = cls._backend()
        try:
            kw: dict[str, Any] = {}
            if backend is _q and (s := cls._style()):
                kw["style"] = s
            result: str | None = backend.select(question, choices=choices, **kw).ask()
            return result
        except Exception:
            return None

    @classmethod
    def confirm(cls, question: str, default: bool = True) -> bool:
        backend = cls._backend()
        try:
            kw: dict[str, Any] = {}
            if backend is _q and (s := cls._style()):
                kw["style"] = s
            result = backend.confirm(question, default=default, **kw).ask()
            return bool(result) if result is not None else False
        except Exception:
            return False

    @classmethod
    def checkbox(cls, question: str, choices: list[str]) -> list[str]:
        backend = cls._backend()
        try:
            kw: dict[str, Any] = {}
            if backend is _q and (s := cls._style()):
                kw["style"] = s
            result = backend.checkbox(question, choices=choices, **kw).ask()
            return result if result is not None else []
        except Exception:
            return []
