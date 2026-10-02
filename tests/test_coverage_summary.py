"""Tests for scripts/coverage_summary.py, the CI job-summary renderer."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "coverage_summary.py"
_spec = importlib.util.spec_from_file_location("coverage_summary", _SCRIPT)
assert _spec is not None and _spec.loader is not None
cs = importlib.util.module_from_spec(_spec)
sys.modules["coverage_summary"] = cs
_spec.loader.exec_module(cs)

_XML = """<?xml version="1.0" ?>
<coverage version="7.13.5" line-rate="0.6">
  <packages><package name="shimkit"><classes>
    <class name="a.py" filename="src/shimkit/a.py">
      <lines><line number="1" hits="1"/><line number="2" hits="1"/></lines>
    </class>
    <class name="b.py" filename="src/shimkit/b.py">
      <lines><line number="1" hits="1"/><line number="2" hits="0"/>
             <line number="3" hits="0"/></lines>
    </class>
  </classes></package></packages>
</coverage>
"""


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "coverage.xml"
    p.write_text(body, encoding="utf-8")
    return p


def test_parse_counts_statements_and_hits(tmp_path: Path) -> None:
    files = cs.parse_coverage_xml(_write(tmp_path, _XML))
    assert [(f.path, f.statements, f.covered) for f in files] == [
        ("src/shimkit/a.py", 2, 2),
        ("src/shimkit/b.py", 3, 1),
    ]


def test_render_lists_lowest_first_and_compares_to_floor(tmp_path: Path) -> None:
    files = cs.parse_coverage_xml(_write(tmp_path, _XML))
    text = cs.render(files, floor=84.0, lowest=10, full=None)
    assert "**Total: 60.00%** (3/5 statements) **below** the enforced floor of **84%**" in text
    assert "Measured across 2 files" in text
    assert text.index("src/shimkit/b.py") < text.index("src/shimkit/a.py")
    assert cs.render(files, floor=50.0, lowest=1, full=None).count("| `src/") == 1


def test_main_appends_to_step_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = tmp_path / "summary.md"
    summary.write_text("earlier step\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.chdir(tmp_path)  # no .coverage here, so no full report
    assert cs.main(["--xml", str(_write(tmp_path, _XML))]) == 0
    text = summary.read_text(encoding="utf-8")
    assert text.startswith("earlier step\n## Coverage")


@pytest.mark.parametrize("body", [None, "<coverage><packages/></coverage>"])
def test_main_refuses_missing_or_empty_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str | None
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    xml = tmp_path / "coverage.xml"
    if body is not None:
        xml.write_text(body, encoding="utf-8")
    assert cs.main(["--xml", str(xml)]) == 1
