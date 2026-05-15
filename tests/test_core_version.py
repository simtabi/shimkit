"""Tests for ``shimkit.core.version``.

Each detector is exercised with offline fixture strings (captured
from real CLI output once, then frozen here). ``CommandRunner.run``
is monkeypatched throughout — no real binaries are invoked.
"""

from __future__ import annotations

import pytest
from packaging.version import Version

from shimkit.core import CommandResult
from shimkit.core import version as v

# ─── pure parser tests per detector ──────────────────────────────────────


def test_docker_detector_parses_server_version() -> None:
    det = v._DETECTORS["docker"]
    assert det.argv[:3] == ["docker", "version", "--format"]
    # docker prints just the version (no decoration).
    assert det.parse("28.5.2\n", "") == "28.5.2"
    assert det.parse("", "") is None


def test_nginx_detector_reads_from_stderr() -> None:
    det = v._DETECTORS["nginx"]
    assert det.parse("", "nginx version: nginx/1.27.2 (Ubuntu)\n") == "1.27.2"
    # And from stdout if stderr is empty (defensive).
    assert det.parse("nginx version: nginx/1.18.0\n", "") == "1.18.0"


def test_git_detector_parses_git_version_string() -> None:
    det = v._DETECTORS["git"]
    assert det.parse("git version 2.42.0\n", "") == "2.42.0"
    assert det.parse("git version 2.39.3 (Apple Git-145)\n", "") == "2.39.3"


def test_gpg_detector_parses_first_line() -> None:
    det = v._DETECTORS["gpg"]
    stdout = "gpg (GnuPG) 2.4.5\nlibgcrypt 1.10.3\nCopyright …\n"
    assert det.parse(stdout, "") == "2.4.5"


def test_python_detector_parses_python_dot_string() -> None:
    det = v._DETECTORS["python"]
    # python3.10 prints to stdout on 3.10+; older was stderr.
    assert det.parse("Python 3.12.7\n", "") == "3.12.7"
    assert det.parse("", "Python 3.9.18\n") == "3.9.18"


# ─── constraint check matrix ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("constraint_min", "constraint_max", "version_str", "expected"),
    [
        (None, None, "1.0.0", v.Status.OK),  # no bound
        ("1.0", None, "1.0.0", v.Status.OK),  # >= bare
        ("1.0", None, "0.9.0", v.Status.OUT_OF_RANGE),
        (None, "<2.0", "1.9.9", v.Status.OK),  # < explicit
        (None, "<2.0", "2.0.0", v.Status.OUT_OF_RANGE),
        ("1.0", "<2.0", "1.5.0", v.Status.OK),  # range
        ("1.0", "<2.0", "0.9", v.Status.OUT_OF_RANGE),
        ("1.0", "<2.0", "2.0.1", v.Status.OUT_OF_RANGE),
        (">=20.10", "<25.0", "24.0.7", v.Status.OK),  # both explicit
        (">=20.10", "<25.0", "25.0.0", v.Status.OUT_OF_RANGE),
    ],
)
def test_constraint_check_matrix(
    constraint_min: str | None,
    constraint_max: str | None,
    version_str: str,
    expected: v.Status,
) -> None:
    c = v.VersionConstraint(min=constraint_min, max=constraint_max)
    assert c.check(Version(version_str)) is expected


def test_constraint_with_unparseable_specifier_returns_out_of_range() -> None:
    c = v.VersionConstraint(min="not-a-version")
    assert c.check(Version("1.0")) is v.Status.OUT_OF_RANGE


# ─── detect() + validate() ──────────────────────────────────────────────


class _FakeRunner:
    """A drop-in for CommandRunner that returns fixed CommandResults."""

    def __init__(self, results_by_argv: dict[str, CommandResult]) -> None:
        self.results_by_argv = results_by_argv
        self.calls: list[list[str]] = []

    def run(self, cmd, **_):  # type: ignore[no-untyped-def]
        self.calls.append(list(cmd))
        key = cmd[0]
        return self.results_by_argv.get(key, CommandResult(1, "", "not found"))


def _stub_which_finds_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "shimkit.core.version.shutil.which",
        lambda binary: f"/usr/bin/{binary}",
    )


def test_detect_returns_none_when_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.core.version.shutil.which", lambda _binary: None)
    assert v.detect("docker") is None


def test_detect_returns_tool_version_for_known_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_which_finds_everything(monkeypatch)
    fake = _FakeRunner({"git": CommandResult(0, "git version 2.42.0\n", "")})
    monkeypatch.setattr("shimkit.core.version.CommandRunner.run", fake.run)
    tv = v.detect("git")
    assert tv is not None
    assert tv.version == Version("2.42.0")
    assert tv.raw == "2.42.0"


def test_detect_returns_unparseable_when_version_doesnt_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_which_finds_everything(monkeypatch)
    # Custom detector via the registry so we can inject a parser
    # that returns something the packaging.Version can't handle.
    fake_det = v.Detector(
        argv=["unicorn", "--version"],
        parse=lambda out, err: "not-a-version",
    )
    monkeypatch.setitem(v._DETECTORS, "unicorn", fake_det)
    monkeypatch.setattr(
        "shimkit.core.version.CommandRunner.run",
        lambda cmd, **_: CommandResult(0, "anything", ""),
    )
    tv = v.detect("unicorn")
    assert tv is not None
    assert tv.version is None
    assert tv.raw == "not-a-version"


def test_detect_for_unknown_tool_returns_none() -> None:
    assert v.detect("not-a-real-tool") is None


def test_validate_status_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_which_finds_everything(monkeypatch)
    monkeypatch.setattr(
        "shimkit.core.version.CommandRunner.run",
        lambda cmd, **_: CommandResult(0, "git version 3.0.0\n", ""),
    )
    r = v.validate("git")
    assert r.status is v.Status.OK
    assert r.tool_version is not None
    assert r.tool_version.version == Version("3.0.0")


def test_validate_status_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_which_finds_everything(monkeypatch)
    monkeypatch.setattr(
        "shimkit.core.version.CommandRunner.run",
        lambda cmd, **_: CommandResult(0, "git version 1.0.0\n", ""),
    )
    r = v.validate("git")
    assert r.status is v.Status.OUT_OF_RANGE
    assert r.remediation is not None  # gets the install hint


def test_validate_status_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.core.version.shutil.which", lambda _: None)
    r = v.validate("docker")
    assert r.status is v.Status.MISSING
    assert r.tool_version is None
    assert r.remediation is not None


def test_validate_status_unparseable(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_which_finds_everything(monkeypatch)
    fake_det = v.Detector(
        argv=["unicorn", "--version"],
        parse=lambda out, err: "v???",
    )
    monkeypatch.setitem(v._DETECTORS, "unicorn", fake_det)
    monkeypatch.setattr(
        "shimkit.core.version.CommandRunner.run",
        lambda cmd, **_: CommandResult(0, "", ""),
    )
    r = v.validate("unicorn")
    assert r.status is v.Status.UNPARSEABLE
    assert r.tool_version is not None
    assert r.tool_version.version is None


def test_validate_all_walks_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.core.version.shutil.which", lambda _: None)
    results = v.validate_all()
    # Every result should report MISSING because we made nothing
    # findable on PATH.
    assert {r.tool for r in results} >= {"docker", "nginx", "git", "gpg", "python"}
    assert all(r.status is v.Status.MISSING for r in results)


# ─── preflight ──────────────────────────────────────────────────────────


def test_preflight_passes_when_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_which_finds_everything(monkeypatch)
    monkeypatch.setattr(
        "shimkit.core.version.CommandRunner.run",
        lambda cmd, **_: CommandResult(0, "git version 2.42.0\n", ""),
    )
    v.preflight(("git",))  # no raise


def test_preflight_raises_on_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.core.version.shutil.which", lambda _: None)
    with pytest.raises(v.VersionViolationError) as exc:
        v.preflight(("docker",))
    assert "docker" in str(exc.value)


def test_preflight_raises_on_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_which_finds_everything(monkeypatch)
    monkeypatch.setattr(
        "shimkit.core.version.CommandRunner.run",
        lambda cmd, **_: CommandResult(0, "git version 1.0.0\n", ""),
    )
    with pytest.raises(v.VersionViolationError):
        v.preflight(("git",))


def test_preflight_with_force_passes_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_which_finds_everything(monkeypatch)
    monkeypatch.setattr(
        "shimkit.core.version.CommandRunner.run",
        lambda cmd, **_: CommandResult(0, "git version 1.0.0\n", ""),
    )
    v.preflight(("git",), force=True)  # no raise


def test_preflight_with_force_still_raises_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.core.version.shutil.which", lambda _: None)
    with pytest.raises(v.VersionViolationError):
        v.preflight(("docker",), force=True)


def test_preflight_unparseable_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_which_finds_everything(monkeypatch)
    fake_det = v.Detector(
        argv=["unicorn", "--version"],
        parse=lambda out, err: "v???",
    )
    monkeypatch.setitem(v._DETECTORS, "unicorn", fake_det)
    monkeypatch.setattr(
        "shimkit.core.version.CommandRunner.run",
        lambda cmd, **_: CommandResult(0, "", ""),
    )
    v.preflight(("unicorn",))  # no raise; warn-only


# ─── constraint loading from config ────────────────────────────────────


def test_constraint_reads_from_config() -> None:
    # The defaults.json has git min="2.30"; constraint() returns
    # the runtime VersionConstraint mirroring that.
    c = v.constraint("git")
    assert c.min == "2.30"


def test_constraint_returns_empty_for_unknown_tool() -> None:
    c = v.constraint("not-a-real-tool")
    assert c.min is None and c.max is None and c.preferred is None


# ─── remediation hints ─────────────────────────────────────────────────


def test_remediation_for_docker_is_platform_specific(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Darwin", machine="arm64")),
    )
    assert "brew" in (v._remediation_for("docker") or "")

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    assert "apt-get" in (v._remediation_for("docker") or "")


def test_remediation_for_unknown_tool_is_none() -> None:
    assert v._remediation_for("not-a-real-tool") is None
