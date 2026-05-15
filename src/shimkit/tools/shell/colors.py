"""``shimkit shell colors`` -- 256-color ANSI palette diagnostic.

Read-only. Useful when a new terminal theme makes shimkit's help
output illegible and you want to see what your terminal actually
renders for each ANSI index.

Three sections:

- 16: the basic + bright ANSI colors (indices 0-15).
- 216: the 6x6x6 color cube (indices 16-231).
- 24: the grayscale ramp (indices 232-255).

``--json`` returns a structured dump with the index + RGB triple
(per Xterm's specified mapping) for every cell, so other tools can
pipe shimkit's idea of the palette into their own renderers.
"""

from __future__ import annotations

from collections.abc import Iterator

from shimkit.core import UI, Event, emit_json

# Xterm 256-color palette (indices 0-255).
# 0-15:    ANSI basic + bright (rendered by the user's terminal theme;
#          we just label them).
# 16-231:  6x6x6 RGB cube with steps {0, 95, 135, 175, 215, 255}.
# 232-255: 24-step grayscale ramp from #080808 to #eeeeee.

_CUBE_STEPS: tuple[int, ...] = (0, 95, 135, 175, 215, 255)


def index_to_rgb(idx: int) -> tuple[int, int, int] | None:
    """Map an ANSI 256 index to its Xterm-specified RGB triple.

    Indices 0-15 are theme-dependent (the terminal's palette is the
    truth), so we return ``None`` rather than guess.

    >>> index_to_rgb(16)
    (0, 0, 0)
    >>> index_to_rgb(231)
    (255, 255, 255)
    >>> index_to_rgb(232)
    (8, 8, 8)
    >>> index_to_rgb(255)
    (238, 238, 238)
    """
    if 0 <= idx <= 15:
        return None
    if 16 <= idx <= 231:
        n = idx - 16
        r = _CUBE_STEPS[n // 36]
        g = _CUBE_STEPS[(n // 6) % 6]
        b = _CUBE_STEPS[n % 6]
        return (r, g, b)
    if 232 <= idx <= 255:
        v = 8 + (idx - 232) * 10
        return (v, v, v)
    return None


def _swatch(idx: int) -> str:
    """One cell -- three-digit index over a background of that color."""
    # Pick black or white foreground for readability against the bg.
    rgb = index_to_rgb(idx)
    if rgb is None:
        fg = "97"  # bright white -- works against the theme either way
    else:
        # Luminance > 128 means a light bg; use black text on top.
        lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
        fg = "30" if lum > 128 else "97"
    return f"\033[48;5;{idx}m\033[{fg}m {idx:>3} \033[0m"


def _basic_grid() -> Iterator[str]:
    """Indices 0-15, two rows of 8."""
    for row in range(2):
        yield "  " + " ".join(_swatch(row * 8 + col) for col in range(8))


def _cube_grid() -> Iterator[str]:
    """Indices 16-231, six 6x6 panels."""
    for plane in range(6):
        for row in range(6):
            cells = (_swatch(16 + plane * 36 + row * 6 + col) for col in range(6))
            yield "  " + " ".join(cells)
        yield ""


def _grayscale_grid() -> Iterator[str]:
    """Indices 232-255, two rows of 12."""
    for row in range(2):
        yield "  " + " ".join(_swatch(232 + row * 12 + col) for col in range(12))


def show(*, json_out: bool = False) -> int:
    """Render the 256-color palette to stdout (or emit JSON)."""
    if json_out:
        emit_json(
            Event(
                tool="shell",
                step="colors",
                status="ok",
                data={
                    "palette": [
                        {
                            "index": i,
                            "section": _section_for(i),
                            "rgb": list(rgb) if (rgb := index_to_rgb(i)) is not None else None,
                        }
                        for i in range(256)
                    ]
                },
            )
        )
        return 0

    UI.header("ANSI 16 (theme-defined)")
    for line in _basic_grid():
        UI.line(line)

    UI.header("6x6x6 cube (indices 16-231)")
    for line in _cube_grid():
        UI.line(line)

    UI.header("Grayscale ramp (indices 232-255)")
    for line in _grayscale_grid():
        UI.line(line)

    UI.dim("Pipe with `--json` for a structured palette dump.")
    return 0


def _section_for(idx: int) -> str:
    if 0 <= idx <= 15:
        return "basic"
    if 16 <= idx <= 231:
        return "cube"
    return "grayscale"
