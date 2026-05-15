"""Tests for ``shimkit shell colors``."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.tools.shell import colors


def test_index_to_rgb_basic_indices_return_none() -> None:
    for idx in range(16):
        assert colors.index_to_rgb(idx) is None


def test_index_to_rgb_cube_endpoints() -> None:
    assert colors.index_to_rgb(16) == (0, 0, 0)
    assert colors.index_to_rgb(231) == (255, 255, 255)


def test_index_to_rgb_grayscale_endpoints() -> None:
    assert colors.index_to_rgb(232) == (8, 8, 8)
    assert colors.index_to_rgb(255) == (238, 238, 238)


def test_index_to_rgb_out_of_range_returns_none() -> None:
    assert colors.index_to_rgb(-1) is None
    assert colors.index_to_rgb(256) is None


@pytest.mark.parametrize(
    ("idx", "section"),
    [
        (0, "basic"),
        (15, "basic"),
        (16, "cube"),
        (231, "cube"),
        (232, "grayscale"),
        (255, "grayscale"),
    ],
)
def test_section_for(idx: int, section: str) -> None:
    assert colors._section_for(idx) == section


def test_show_to_stdout(runner: CliRunner) -> None:
    result = runner.invoke(app, ["shell", "colors"])
    assert result.exit_code == 0
    # Header strings appear; ANSI body too.
    assert "ANSI 16" in result.stdout
    assert "cube" in result.stdout
    assert "Grayscale" in result.stdout


def test_show_json_returns_256_entries(runner: CliRunner) -> None:
    result = runner.invoke(app, ["shell", "colors", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    palette = doc["data"]["palette"]
    assert len(palette) == 256
    # Basic indices have no RGB.
    assert palette[0]["rgb"] is None
    assert palette[0]["section"] == "basic"
    # Cube endpoints have known RGB.
    assert palette[16]["rgb"] == [0, 0, 0]
    assert palette[231]["rgb"] == [255, 255, 255]
    # Grayscale section labels.
    assert palette[232]["section"] == "grayscale"
