"""Tool-version detection + constraint enforcement.

One source of truth (the config registry under ``tools.versions``)
consulted at three enforcement points:

1. Install-time documentation (rendered offline from the registry).
2. Runtime preflight (``Manager.boot()`` calls ``preflight((...,))``).
3. On-demand audit (``shimkit doctor`` calls ``validate_all()``).

Four distinct outcomes:

- :attr:`Status.OK` — detected version satisfies the constraint.
- :attr:`Status.OUT_OF_RANGE` — version detected, falls outside the
  declared range. Default: exit 69 unless ``--force``.
- :attr:`Status.MISSING` — binary not on PATH or detector exited
  non-zero. Exit 69; ``--force`` cannot conjure a missing binary.
- :attr:`Status.UNPARSEABLE` — binary present, output didn't parse
  as a SemVer-ish version. Warn-only; we don't brick the user when
  a vendor changes their version-string format.

Examples
--------

>>> from shimkit.core import version
>>> result = version.validate("docker")
>>> result.status                                       # doctest: +SKIP
<Status.OK: 'ok'>
>>> version.preflight(("docker",))                       # doctest: +SKIP
>>> all_results = version.validate_all()                 # doctest: +SKIP
"""

from __future__ import annotations

import re
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from .command import CommandRunner
from .platform import Platform

__all__ = [
    "Detector",
    "Result",
    "Status",
    "ToolVersion",
    "VersionConstraint",
    "VersionViolationError",
    "constraint",
    "detect",
    "preflight",
    "validate",
    "validate_all",
]


class Status(str, Enum):
    """The four outcomes the detector + constraint can produce."""

    OK = "ok"
    OUT_OF_RANGE = "out_of_range"
    MISSING = "missing"
    UNPARSEABLE = "unparseable"


@dataclass(frozen=True)
class ToolVersion:
    """One detected (tool, version) pair.

    ``version`` is ``None`` when the detector ran but the output
    didn't parse — the original ``raw`` string is kept for display.
    """

    name: str
    version: Version | None
    raw: str


@dataclass(frozen=True)
class VersionConstraint:
    """User-declarable range of acceptable versions for one tool.

    All three fields are optional. ``min`` / ``max`` accept either a
    bare version (interpreted as ``>=`` / ``<=`` respectively) or an
    explicit specifier (``"<25.0"``, ``">=20.10"``, etc.).
    ``preferred`` is purely informational — surfaced by
    ``shimkit doctor`` as an upgrade hint, never enforced.

    >>> c = VersionConstraint(min="20.10", max="<25.0")
    >>> from packaging.version import Version
    >>> c.check(Version("24.0.7"))
    <Status.OK: 'ok'>
    >>> c.check(Version("19.03.0"))
    <Status.OUT_OF_RANGE: 'out_of_range'>
    """

    min: str | None = None
    max: str | None = None
    preferred: str | None = None

    def to_specifier_set(self) -> SpecifierSet:
        parts: list[str] = []
        if self.min:
            parts.append(_normalise_bound(self.min, default_op=">="))
        if self.max:
            parts.append(_normalise_bound(self.max, default_op="<="))
        return SpecifierSet(",".join(parts) if parts else "")

    def check(self, v: Version) -> Status:
        """``OK`` if ``v`` satisfies the spec, ``OUT_OF_RANGE`` otherwise."""
        try:
            spec = self.to_specifier_set()
        except InvalidSpecifier:
            # User config error — surface as out-of-range so they
            # notice. The cleaner fix is to validate at config-load
            # time, but that adds a layer; here is fine.
            return Status.OUT_OF_RANGE
        if not spec:
            return Status.OK
        return Status.OK if v in spec else Status.OUT_OF_RANGE


@dataclass(frozen=True)
class Detector:
    """How shimkit asks a tool for its version string."""

    argv: list[str]
    # parse(stdout, stderr) → version string | None
    parse: Callable[[str, str], str | None] = field(default=lambda out, _err: out.strip() or None)

    def run(self, *, runner: type[CommandRunner] = CommandRunner) -> ToolVersion | None:
        """Invoke the detector. Returns ``None`` if the binary is missing
        OR if the command itself errored. Returns a :class:`ToolVersion`
        with ``version=None`` if the binary ran but its output didn't
        parse (the caller will surface ``UNPARSEABLE``)."""
        binary = self.argv[0]
        if shutil.which(binary) is None:
            return None
        r = runner.run(self.argv)
        # Many version-printing tools exit non-zero on first run, on
        # `--help` aliasing, or after first-run prompts. Don't treat
        # rc != 0 as fatal — let the parser decide if output is usable.
        raw = self.parse(r.stdout, r.stderr) or ""
        if not raw:
            return None
        try:
            return ToolVersion(name=binary, version=Version(raw), raw=raw)
        except InvalidVersion:
            return ToolVersion(name=binary, version=None, raw=raw)


@dataclass(frozen=True)
class Result:
    """Outcome of one (tool, constraint) validation pass."""

    tool: str
    status: Status
    tool_version: ToolVersion | None
    constraint: VersionConstraint
    remediation: str | None = None


class VersionViolationError(RuntimeError):
    """Raised by :func:`preflight` when a required tool fails the
    constraint check and ``force`` is False."""

    def __init__(self, results: list[Result]) -> None:
        self.results = results
        msg = "; ".join(f"{r.tool}: {r.status.value}" for r in results)
        super().__init__(msg)


# ─── Detector registry ─────────────────────────────────────────────────


def _re_match(pattern: str, text: str) -> str | None:
    """Search ``text`` for the first match of ``pattern`` (group 1)."""
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1) if m else None


_DETECTORS: dict[str, Detector] = {
    "docker": Detector(
        argv=["docker", "version", "--format", "{{.Server.Version}}"],
    ),
    "nginx": Detector(
        # nginx -v writes "nginx version: nginx/1.27.0" to stderr.
        argv=["nginx", "-v"],
        parse=lambda out, err: _re_match(r"nginx/([\d.]+)", err or out),
    ),
    "git": Detector(
        argv=["git", "--version"],
        parse=lambda out, _err: _re_match(r"git version ([\d.]+)", out),
    ),
    "gpg": Detector(
        argv=["gpg", "--version"],
        parse=lambda out, _err: _re_match(r"gpg \(GnuPG\)[^\d]*([\d.]+)", out),
    ),
    "python": Detector(
        argv=[sys.executable, "--version"],
        parse=lambda out, err: _re_match(r"Python ([\d.]+)", out or err),
    ),
}


# ─── Public API ────────────────────────────────────────────────────────


def detect(tool: str, *, runner: type[CommandRunner] = CommandRunner) -> ToolVersion | None:
    """Run the registered detector for ``tool``.

    Returns ``None`` when the tool isn't in the registry, the binary
    isn't on PATH, or the detector command itself failed entirely. A
    binary that ran but printed an unparseable version returns a
    :class:`ToolVersion` with ``version=None``.

    >>> tv = detect("git")                              # doctest: +SKIP
    >>> tv is None or tv.name == "git"                   # doctest: +SKIP
    True
    """
    det = _DETECTORS.get(tool)
    if det is None:
        return None
    return det.run(runner=runner)


def constraint(tool: str) -> VersionConstraint:
    """Read the constraint declared for ``tool`` in
    ``get_config().tools.versions``. Returns an empty
    :class:`VersionConstraint` if no entry exists.

    The config layer uses a pydantic model with the same shape; we
    convert it to the runtime dataclass so callers get the
    ``check()`` / ``to_specifier_set()`` methods.
    """
    from shimkit.config import get_config

    vc = getattr(get_config().tools.versions, tool, None)
    if vc is None:
        return VersionConstraint()
    return VersionConstraint(
        min=vc.min,
        max=vc.max,
        preferred=vc.preferred,
    )


def validate(tool: str, *, runner: type[CommandRunner] = CommandRunner) -> Result:
    """Detect + check + remediate. Returns a :class:`Result`."""
    cons = constraint(tool)
    tv = detect(tool, runner=runner)
    if tv is None:
        return Result(
            tool=tool,
            status=Status.MISSING,
            tool_version=None,
            constraint=cons,
            remediation=_remediation_for(tool),
        )
    if tv.version is None:
        return Result(
            tool=tool,
            status=Status.UNPARSEABLE,
            tool_version=tv,
            constraint=cons,
            remediation=None,
        )
    return Result(
        tool=tool,
        status=cons.check(tv.version),
        tool_version=tv,
        constraint=cons,
        remediation=_remediation_for(tool)
        if cons.check(tv.version) is Status.OUT_OF_RANGE
        else None,
    )


def validate_all(*, runner: type[CommandRunner] = CommandRunner) -> list[Result]:
    """Validate every tool the detector registry knows about. Order is
    stable across runs (the registry's insertion order).
    """
    return [validate(name, runner=runner) for name in _DETECTORS]


def preflight(
    tools: Sequence[str],
    *,
    force: bool = False,
    runner: type[CommandRunner] = CommandRunner,
) -> None:
    """Raise :class:`VersionViolationError` if any of ``tools`` fails the
    constraint check (and ``force`` is ``False``).

    Status-to-behavior matrix:

    +----------------+------------------+----------------+
    | Status         | force=False      | force=True     |
    +================+==================+================+
    | OK             | proceed          | proceed        |
    +----------------+------------------+----------------+
    | OUT_OF_RANGE   | raise            | proceed        |
    +----------------+------------------+----------------+
    | MISSING        | raise            | raise          |
    +----------------+------------------+----------------+
    | UNPARSEABLE    | proceed          | proceed        |
    +----------------+------------------+----------------+

    The caller is responsible for mapping :class:`VersionViolationError`
    to ``sys.exit(EX_UNAVAILABLE)`` (69). ``Manager.boot()`` does
    this directly so test harnesses observe ``SystemExit``.
    """
    bad: list[Result] = []
    for tool in tools:
        r = validate(tool, runner=runner)
        if r.status is Status.OK:
            continue
        if r.status is Status.UNPARSEABLE:
            continue  # warn-only; preflight doesn't bail
        if r.status is Status.OUT_OF_RANGE and force:
            continue  # forced through with a warning at the call site
        bad.append(r)
    if bad:
        raise VersionViolationError(bad)


# ─── Internals ─────────────────────────────────────────────────────────


_OP_PREFIXES: tuple[str, ...] = ("<=", ">=", "==", "!=", "~=", "<", ">")


def _normalise_bound(bound: str, *, default_op: str) -> str:
    """Accept either a bare version (``"20.10"``) or an explicit
    specifier (``"<25.0"``). Returns a fragment suitable for
    :class:`SpecifierSet`.
    """
    s = bound.strip()
    if any(s.startswith(op) for op in _OP_PREFIXES):
        return s
    return f"{default_op}{s}"


def _remediation_for(tool: str) -> str | None:
    """Best-effort install hint for ``tool`` on the current platform.

    Cheap rather than authoritative — we suggest the most common
    package-manager command and leave perfect taste to the user.
    """
    plat = Platform.detect()
    table = _REMEDIATION_TABLE.get(tool, {})
    if plat.is_macos:
        return table.get("macos")
    if plat.is_linux:
        return table.get("linux")
    return None


_REMEDIATION_TABLE: dict[str, dict[str, str]] = {
    "docker": {
        "macos": "brew install --cask docker",
        "linux": "apt-get install docker.io  # or distro equivalent",
    },
    "nginx": {
        "macos": "brew install nginx",
        "linux": "apt-get install nginx  # or distro equivalent",
    },
    "git": {
        "macos": "brew install git  (or `xcode-select --install`)",
        "linux": "apt-get install git  # or distro equivalent",
    },
    "gpg": {
        "macos": "brew install gnupg",
        "linux": "apt-get install gnupg  # or distro equivalent",
    },
    "python": {
        "macos": "brew install python@3.12",
        "linux": "apt-get install python3.12  # or distro equivalent",
    },
}
