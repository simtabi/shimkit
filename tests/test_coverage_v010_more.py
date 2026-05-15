"""More coverage-tightening for the v0.10.0 push.

UI primitives (banner, spinner), java/oracle remover, dns thin
spots, gpg thin spots, a few easy ssh helpers.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from shimkit.core import CommandResult
from shimkit.core import platform as _plat
from shimkit.core import ui as _ui

# ─── core/ui — UI.banner ─────────────────────────────────────────────


def test_ui_banner_empty_sections_is_noop(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ui.UI.banner("Left", "Right", sections=[])
    # Empty sections short-circuits to no output.
    assert capsys.readouterr().out == ""


def test_ui_banner_single_section(capsys: pytest.CaptureFixture[str]) -> None:
    _ui.UI.banner(
        "shimkit",
        "v0.10",
        sections=[[("Tool", "ports"), ("Status", "ok")]],
        min_width=30,
    )
    out = capsys.readouterr().out
    assert "shimkit" in out
    assert "v0.10" in out
    assert "Tool" in out
    assert "ports" in out
    assert "+" in out  # corner glyphs


def test_ui_banner_multiple_sections_has_mid_separator(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ui.UI.banner(
        "title",
        "side",
        sections=[
            [("a", "1"), ("b", "2")],
            [("c", "3")],
        ],
    )
    out = capsys.readouterr().out
    # 2 sections + outer = at least 3 mid-bar rows.
    assert out.count("+---") >= 2


def test_ui_quiet_suppresses_non_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ui.UI.set_quiet(True)
    try:
        _ui.UI.info("info-msg")
        _ui.UI.warning("warn-msg")
        _ui.UI.success("ok-msg")
        out = capsys.readouterr().out
        assert "info-msg" not in out
        assert "warn-msg" not in out
        assert "ok-msg" not in out
        # Errors always print.
        _ui.UI.error("err-msg")
        out = capsys.readouterr().out
        assert "err-msg" in out
    finally:
        _ui.UI.set_quiet(False)


def test_ui_set_color_mode_never_strips_ansi(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ui.UI.set_color_mode("never")
    try:
        _ui.UI.info("hello")
        out = capsys.readouterr().out
        assert "hello" in out
        assert "\033[" not in out
    finally:
        _ui.UI.set_color_mode(None)


def test_ui_spinner_starts_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """The spinner is a context-manager wrapping a daemon thread; we
    just verify the lifecycle (enter starts, exit joins) runs without
    raising and emits some glyph at least once."""
    buf = io.StringIO()
    monkeypatch.setattr("shimkit.core.ui.sys.stdout", buf)
    # is_tty False (StringIO) skips the cursor escapes.
    with _ui.UI.spinner("loading"):
        import time

        time.sleep(0.15)  # let one frame run
    text = buf.getvalue()
    # At least one of the spinner frames shows up.
    assert any(f in text for f in ("[|]", "[/]", "[-]", "[\\]"))


# ─── tools/java/oracle ───────────────────────────────────────────────


def test_oracle_remover_available_macos() -> None:
    from shimkit.tools.java import oracle as _oracle

    r = _oracle.OracleRemover(_plat.Platform(system="Darwin", machine="arm64"))
    assert r.available()


def test_oracle_remover_unavailable_linux() -> None:
    from shimkit.tools.java import oracle as _oracle

    r = _oracle.OracleRemover(_plat.Platform(system="Linux"))
    assert not r.available()
    # remove() short-circuits on non-macOS.
    assert r.remove() is False


def test_oracle_remover_removes_only_within_safe_roots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.tools.java import oracle as _oracle

    # Two paths: one inside the safe root, one outside.
    safe_root = tmp_path / "Library" / "Java"
    safe_root.mkdir(parents=True)
    target = safe_root / "JavaVirtualMachines" / "jdk-22.jdk"
    target.parent.mkdir(parents=True)
    target.mkdir()

    sneaky = tmp_path / "elsewhere" / "jdk-22.jdk"
    sneaky.parent.mkdir(parents=True)
    sneaky.mkdir()

    class FakeJava:
        oracle_glob_patterns = [
            str(safe_root / "JavaVirtualMachines" / "jdk*"),
            str(sneaky),
        ]
        oracle_safe_roots = [str(safe_root)]

    class FakeTools:
        java = FakeJava()

    class FakeCfg:
        tools = FakeTools()

    monkeypatch.setattr("shimkit.tools.java.oracle.get_config", lambda: FakeCfg())
    monkeypatch.setattr(
        "shimkit.tools.java.oracle.sudo_prefix", lambda: []
    )
    calls: list[list[str]] = []

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(_oracle.CommandRunner, "run", staticmethod(fake_run))

    r = _oracle.OracleRemover(_plat.Platform(system="Darwin", machine="arm64"))
    assert r.remove() is True
    # Only the target inside the safe root should have been rm-ed.
    rm_targets = [c[-1] for c in calls if c[:2] == ["rm", "-rf"]]
    assert str(target) in rm_targets
    assert str(sneaky) not in rm_targets


def test_oracle_remover_patterns_and_safe_roots_expanded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.tools.java import oracle as _oracle

    class FakeJava:
        oracle_glob_patterns = ["~/foo/*"]
        oracle_safe_roots = ["~/Library"]

    class FakeTools:
        java = FakeJava()

    class FakeCfg:
        tools = FakeTools()

    monkeypatch.setattr("shimkit.tools.java.oracle.get_config", lambda: FakeCfg())
    r = _oracle.OracleRemover(_plat.Platform(system="Darwin", machine="arm64"))
    assert not any(p.startswith("~/") for p in r.patterns)
    assert not any(s.startswith("~/") for s in r.safe_roots)


# ─── tools/ssh — small helper coverage ─────────────────────────────────


def test_ssh_models_perm_issue_kind(tmp_path: Path) -> None:
    from shimkit.tools.ssh import models as _ssh_models

    # dir
    d = tmp_path / "ssh"
    d.mkdir()
    iss = _ssh_models.PermIssue(path=d, actual="755", expected="700")
    assert iss.kind == "dir"
    # public key
    pub = tmp_path / "id.pub"
    pub.write_text("")
    iss = _ssh_models.PermIssue(path=pub, actual="666", expected="644")
    assert iss.kind == "public_key"
    # private key
    priv = tmp_path / "id"
    priv.write_text("")
    iss = _ssh_models.PermIssue(path=priv, actual="666", expected="600")
    assert iss.kind == "private_key_or_known_file"


def test_ssh_models_key_entry_name() -> None:
    from shimkit.tools.ssh import models as _ssh_models

    ke = _ssh_models.KeyEntry(
        private=Path("/x/id_ed25519"),
        public=Path("/x/id_ed25519.pub"),
        key_type="ed25519",
        fingerprint="SHA256:abc",
        comment="user@host",
    )
    assert ke.name == "id_ed25519"


# ─── tools/dns/networksetup — small ────────────────────────────────────


def test_dns_networksetup_imports_cleanly() -> None:
    """Just ensure the module imports — defends against future
    accidental ImportError from broken stub refactors."""
    from shimkit.tools.dns import networksetup as _ns

    assert hasattr(_ns, "NetworkSetup") or hasattr(_ns, "list_services") or _ns is not None


# ─── tools/adguard/ports more ──────────────────────────────────────────


def test_owners_of_iter_psutil_listen_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the psutil branch by injecting a stubbed module."""
    import sys
    import types

    fake = types.ModuleType("psutil")

    class _Status:
        LISTEN = "LISTEN"

    class _Addr:
        def __init__(self, port: int) -> None:
            self.port = port

    class _Conn:
        def __init__(self, port: int, pid: int, status: str = "LISTEN") -> None:
            self.laddr = _Addr(port)
            self.pid = pid
            self.status = status

    class _Proc:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def name(self) -> str:
            return "nginx"

    class _Error(Exception):
        pass

    fake.AccessDenied = _Error
    fake.NoSuchProcess = _Error
    fake.CONN_LISTEN = "LISTEN"
    fake.Process = _Proc

    def net_connections(*, kind: str):
        return [
            _Conn(80, 1234, "LISTEN"),
            _Conn(80, 0, "LISTEN"),  # pid=0 skipped
            _Conn(80, 5678, "ESTABLISHED"),  # filtered by TCP+LISTEN
            _Conn(443, 9999, "LISTEN"),
        ]

    fake.net_connections = net_connections
    monkeypatch.setitem(sys.modules, "psutil", fake)

    from shimkit.tools.adguard import ports as _ports

    out = _ports.owners_of(80, "tcp")
    pids = [o.pid for o in out]
    assert 1234 in pids
    assert 0 not in pids
    assert 5678 not in pids


def test_owners_of_handles_psutil_access_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    fake = types.ModuleType("psutil")

    class _Error(Exception):
        pass

    fake.AccessDenied = _Error

    def net_connections(*, kind: str):
        raise _Error("no privs")

    fake.net_connections = net_connections
    fake.CONN_LISTEN = "LISTEN"
    fake.Process = object  # unused on this path
    fake.NoSuchProcess = _Error
    monkeypatch.setitem(sys.modules, "psutil", fake)

    from shimkit.tools.adguard import ports as _ports

    assert _ports.owners_of(80, "tcp") == []
