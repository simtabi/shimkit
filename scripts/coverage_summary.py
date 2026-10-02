#!/usr/bin/env python3
"""Render a Markdown coverage summary from ``coverage.xml``.

CI appends the output to ``$GITHUB_STEP_SUMMARY`` so every run shows its
coverage on the run page, whether or not Codecov accepted the upload. It
uses only the standard library and the ``coverage`` package that
``pytest-cov`` already installs, so no third-party action is involved.

Usage::

    python scripts/coverage_summary.py [--xml coverage.xml] [--lowest 10]

Writes to ``$GITHUB_STEP_SUMMARY`` when that is set (appending, as GitHub
expects), otherwise to stdout. Exits non-zero when the XML is missing or
lists no files, so a report that measured nothing is never rendered as a
clean summary.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileCoverage:
    path: str
    statements: int
    covered: int

    @property
    def missed(self) -> int:
        return self.statements - self.covered

    @property
    def percent(self) -> float:
        return 100.0 if self.statements == 0 else 100.0 * self.covered / self.statements


def parse_coverage_xml(path: Path) -> list[FileCoverage]:
    """Return one entry per source file in a Cobertura ``coverage.xml``."""
    root = ET.parse(path).getroot()
    files: dict[str, FileCoverage] = {}
    for cls in root.iter("class"):
        filename = cls.get("filename", "")
        lines = cls.findall("./lines/line")
        covered = sum(1 for line in lines if int(line.get("hits", "0")) > 0)
        prev = files.get(filename)
        if prev is not None:  # coverage.py emits one <class> per file, but be safe
            files[filename] = FileCoverage(
                filename, prev.statements + len(lines), prev.covered + covered
            )
        else:
            files[filename] = FileCoverage(filename, len(lines), covered)
    return sorted(files.values(), key=lambda f: f.path)


def configured_floor() -> float | None:
    """The ``fail_under`` coverage.py itself enforces, read through its own config."""
    try:
        import coverage
    except ImportError:
        return None
    value = coverage.Coverage().get_option("report:fail_under")
    return float(value) if value else None


def full_report() -> str | None:
    """``coverage report --format=markdown`` (coverage.py >= 7.0), if the data file exists."""
    if not Path(".coverage").exists():
        return None
    # Exit status 2 means "below fail_under"; the table is still complete.
    proc = subprocess.run(  # fixed argv, no shell
        [sys.executable, "-m", "coverage", "report", "--format=markdown"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() or None


def render(files: list[FileCoverage], floor: float | None, lowest: int, full: str | None) -> str:
    statements = sum(f.statements for f in files)
    covered = sum(f.covered for f in files)
    total = 100.0 if statements == 0 else 100.0 * covered / statements

    out = ["## Coverage", ""]
    if floor is None:
        out.append(f"**Total: {total:.2f}%** ({covered}/{statements} statements, no floor set)")
    else:
        verdict = "meets" if total >= floor else "**below**"
        out.append(
            f"**Total: {total:.2f}%** ({covered}/{statements} statements) "
            f"{verdict} the enforced floor of **{floor:g}%** "
            "(`[tool.coverage.report] fail_under`)."
        )
    out += [
        "",
        f"Measured across {len(files)} files. Lowest-covered:",
        "",
        "| File | Stmts | Miss | Cover |",
        "|---|---:|---:|---:|",
    ]
    for f in sorted(files, key=lambda f: (f.percent, -f.missed))[:lowest]:
        out.append(f"| `{f.path}` | {f.statements} | {f.missed} | {f.percent:.1f}% |")
    if full:
        out += ["", "<details><summary>Full report</summary>", "", full, "", "</details>"]
    out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--xml", type=Path, default=Path("coverage.xml"))
    parser.add_argument("--lowest", type=int, default=10)
    args = parser.parse_args(argv)

    if not args.xml.is_file():
        print(f"::error::{args.xml} not found; nothing to summarise", file=sys.stderr)
        return 1
    files = parse_coverage_xml(args.xml)
    if not files:
        print(
            f"::error::{args.xml} lists no files; refusing to report 0 as a result", file=sys.stderr
        )
        return 1

    text = render(files, configured_floor(), args.lowest, full_report())
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
