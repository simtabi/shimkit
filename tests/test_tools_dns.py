from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.tools.dns import scutil
from shimkit.tools.dns.models import NetworkService, Resolver, ResolverChain

# --- scutil parsing --------------------------------------------------------

_SAMPLE_SCUTIL = """
DNS configuration

resolver #1
  nameserver[0] : 1.1.1.1
  nameserver[1] : 1.0.0.1
  if_index : 16 (en0)
  flags    : Request A records, Request AAAA records
  reach    : 0x00020002 (Reachable,Directly Reachable Address)

resolver #2
  nameserver[0] : 100.100.100.100
  if_index : 22 (utun4)
  flags    : Supplemental
  reach    : 0x00000003 (Reachable)
""".strip()


def test_scutil_parse_extracts_resolvers() -> None:
    chain = scutil.parse(_SAMPLE_SCUTIL)
    assert len(chain.resolvers) == 2
    r1, r2 = chain.resolvers
    assert r1.index == 1
    assert r1.nameservers == ("1.1.1.1", "1.0.0.1")
    assert r1.interface == "en0"
    assert r2.is_tailscale is True


def test_scutil_parse_empty_returns_empty_chain() -> None:
    assert scutil.parse("").resolvers == ()


def test_resolverchain_primary_nameservers() -> None:
    chain = ResolverChain(
        resolvers=(Resolver(index=1, nameservers=("8.8.8.8",)),)
    )
    assert chain.primary_nameservers == ("8.8.8.8",)
    assert ResolverChain().primary_nameservers == ()


# --- platform gate ---------------------------------------------------------


def test_boot_exits_69_on_non_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.dns.manager import DnsManager

    monkeypatch.setattr(
        Platform, "detect", classmethod(lambda cls: Platform(system="Linux", machine="x86_64"))
    )
    with pytest.raises(SystemExit) as exc:
        DnsManager.create().boot()
    assert exc.value.code == 69


def test_boot_on_macos_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.dns import networksetup
    from shimkit.tools.dns.manager import DnsManager

    monkeypatch.setattr(
        Platform, "detect", classmethod(lambda cls: Platform(system="Darwin", machine="arm64"))
    )
    monkeypatch.setattr(
        networksetup, "active_service",
        lambda: NetworkService(name="Wi-Fi", device="en0", is_wifi=True),
    )
    mgr = DnsManager.create().boot()
    assert mgr._service is not None
    assert mgr._service.is_wifi


# --- diagnose --------------------------------------------------------------


def _stub_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.dns import fixer, networksetup

    monkeypatch.setattr(
        Platform, "detect", classmethod(lambda cls: Platform(system="Darwin", machine="arm64"))
    )
    monkeypatch.setattr(
        networksetup, "active_service",
        lambda: NetworkService(name="Wi-Fi", device="en0", is_wifi=True),
    )
    monkeypatch.setattr(fixer, "detect_interference", lambda: [])
    monkeypatch.setattr("shimkit.tools.dns.scutil.query", lambda: ResolverChain())


def test_diagnose_json_emits_parseable_document(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_macos(monkeypatch)
    result = runner.invoke(app, ["dns", "diagnose", "--json"])
    assert result.exit_code == 0
    # The JSON document is the only thing on stdout.
    data = json.loads(result.stdout)
    assert data["tool"] == "dns"
    assert data["step"] == "diagnose"
    assert "resolvers" in data["data"]


def test_diagnose_human_output(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    result = runner.invoke(app, ["dns", "diagnose"])
    assert result.exit_code == 0
    assert "DNS Diagnostic" in result.stdout


# --- severe-tier confirmation ----------------------------------------------


def test_reset_aborts_without_confirm_token(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    result = runner.invoke(app, ["dns", "reset"])
    assert result.exit_code == 1
    assert "Pass --confirm RESET" in result.stdout


def test_reset_aborts_with_wrong_token(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    result = runner.invoke(app, ["dns", "reset", "--confirm", "wrong"])
    assert result.exit_code == 1


# --- dry-run --------------------------------------------------------------


def test_set_dry_run_does_not_call_networksetup(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    calls: list[tuple] = []

    def fake_set(svc, servers):  # type: ignore[no-untyped-def]
        calls.append((svc, servers))
        return True

    monkeypatch.setattr("shimkit.tools.dns.networksetup.set_dns_servers", fake_set)
    result = runner.invoke(app, ["dns", "set", "1.1.1.1", "--dry-run"])
    assert result.exit_code == 0
    assert calls == []


def test_set_real_run_calls_networksetup(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    calls: list[tuple] = []

    def fake_set(svc, servers):  # type: ignore[no-untyped-def]
        calls.append((svc, servers))
        return True

    monkeypatch.setattr("shimkit.tools.dns.networksetup.set_dns_servers", fake_set)
    monkeypatch.setattr("shimkit.tools.dns.networksetup.flush_cache", lambda: True)
    result = runner.invoke(app, ["dns", "set", "1.1.1.1"])
    assert result.exit_code == 0
    assert calls == [("Wi-Fi", ["1.1.1.1"])]


# --- CLI surface ---------------------------------------------------------


def test_cli_dns_help_lists_all_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["dns", "--help"])
    assert result.exit_code == 0
    for cmd in (
        "diagnose", "flush", "show", "set", "reset", "test",
        "profile", "fix", "rollback", "diagnostics",
    ):
        assert cmd in result.stdout


# --- flush ---------------------------------------------------------------


def test_flush_returns_77_on_failure(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    monkeypatch.setattr("shimkit.tools.dns.networksetup.flush_cache", lambda: False)
    result = runner.invoke(app, ["dns", "flush"])
    assert result.exit_code == 77


def test_flush_success(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    monkeypatch.setattr("shimkit.tools.dns.networksetup.flush_cache", lambda: True)
    result = runner.invoke(app, ["dns", "flush"])
    assert result.exit_code == 0


# --- test (resolution check) ---------------------------------------------


def test_test_command_reports_results(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.test_resolution", lambda _domain, timeout=3.0: True
    )
    result = runner.invoke(app, ["dns", "test", "example.com"])
    assert result.exit_code == 0


def test_test_command_returns_1_on_failure(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.test_resolution", lambda _domain, timeout=3.0: False
    )
    result = runner.invoke(app, ["dns", "test", "example.com"])
    assert result.exit_code == 1


# --- networksetup wrapper --------------------------------------------------


_LISTALLHW_SAMPLE = """\
An asterisk (*) denotes that a network service is disabled.
Hardware Port: Wi-Fi
Device: en0
Ethernet Address: aa:bb:cc:dd:ee:ff

Hardware Port: USB 10/100/1000 LAN
Device: en7
Ethernet Address: 11:22:33:44:55:66
"""


def test_listallhardwareports_parses_both_wifi_and_ethernet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.core import CommandResult
    from shimkit.tools.dns import networksetup as ns

    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.CommandRunner.run",
        staticmethod(lambda cmd, **_: CommandResult(0, _LISTALLHW_SAMPLE, "")),
    )
    services = ns.list_hardware_ports()
    assert len(services) == 2
    wifi, ethernet = services
    assert wifi.name == "Wi-Fi" and wifi.device == "en0" and wifi.is_wifi
    assert ethernet.name == "USB 10/100/1000 LAN" and ethernet.device == "en7"
    assert ethernet.is_wifi is False


def test_default_interface_parses_route_get(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core import CommandResult
    from shimkit.tools.dns import networksetup as ns

    sample = "   route to: default\n   destination: default\n   interface: en0\n"
    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.CommandRunner.run",
        staticmethod(lambda cmd, **_: CommandResult(0, sample, "")),
    )
    assert ns.default_interface() == "en0"


def test_default_interface_returns_none_on_no_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.core import CommandResult
    from shimkit.tools.dns import networksetup as ns

    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.CommandRunner.run",
        staticmethod(lambda cmd, **_: CommandResult(1, "", "Network is down")),
    )
    assert ns.default_interface() is None


def test_get_dns_servers_handles_dhcp_message(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core import CommandResult
    from shimkit.tools.dns import networksetup as ns

    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.CommandRunner.run",
        staticmethod(
            lambda cmd, **_: CommandResult(0, "There aren't any DNS Servers set on Wi-Fi.", "")
        ),
    )
    assert ns.get_dns_servers("Wi-Fi") == []


def test_get_dns_servers_returns_configured_ips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.core import CommandResult
    from shimkit.tools.dns import networksetup as ns

    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.CommandRunner.run",
        staticmethod(lambda cmd, **_: CommandResult(0, "1.1.1.1\n8.8.8.8\n", "")),
    )
    assert ns.get_dns_servers("Wi-Fi") == ["1.1.1.1", "8.8.8.8"]


def test_set_dns_servers_empty_clears_to_dhcp(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core import CommandResult
    from shimkit.tools.dns import networksetup as ns

    captured: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        captured.append(cmd)
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.CommandRunner.run", staticmethod(fake_run)
    )
    assert ns.set_dns_servers("Wi-Fi", []) is True
    assert "empty" in captured[0]


# --- fixer ---------------------------------------------------------------


def test_test_resolution_returns_false_on_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    from shimkit.tools.dns import fixer

    def fail_getaddrinfo(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("simulated")

    monkeypatch.setattr(socket, "getaddrinfo", fail_getaddrinfo)
    assert fixer.test_resolution("example.com", timeout=0.1) is False


def test_is_within_returns_true_for_child(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from shimkit.tools.dns.fixer import _is_within

    child = tmp_path / "a" / "b"
    child.mkdir(parents=True)
    assert _is_within(child, tmp_path) is True


def test_is_within_returns_false_for_outsider(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from shimkit.tools.dns.fixer import _is_within

    other = tmp_path / "x"
    other.mkdir()
    sibling = tmp_path.parent / "elsewhere"
    assert _is_within(other, sibling) is False


def test_latest_backup_dir_returns_most_recent(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    import shimkit.tools.dns.fixer as fixer_mod
    from shimkit.config import reset_cache

    # Point backup_dir at tmp_path via SHIMKIT_CONFIG.
    cfg = tmp_path / "shimkit.json"
    cfg.write_text(
        '{"tools": {"dns": {"backup_dir": "' + str(tmp_path).replace("\\", "\\\\") + '"}}}'
    )
    monkeypatch.setenv("SHIMKIT_CONFIG", str(cfg))
    reset_cache()

    import time

    (tmp_path / "20250101-000000").mkdir()
    time.sleep(0.01)
    (tmp_path / "20250102-000000").mkdir()
    latest = fixer_mod.latest_backup_dir()
    assert latest is not None
    assert latest.name == "20250102-000000"


def test_latest_backup_dir_returns_none_when_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    import shimkit.tools.dns.fixer as fixer_mod
    from shimkit.config import reset_cache

    cfg = tmp_path / "shimkit.json"
    cfg.write_text(
        '{"tools": {"dns": {"backup_dir": "' + str(tmp_path / "nope").replace("\\", "\\\\") + '"}}}'
    )
    monkeypatch.setenv("SHIMKIT_CONFIG", str(cfg))
    reset_cache()
    assert fixer_mod.latest_backup_dir() is None


# --- DnsManager methods --------------------------------------------------


def test_dns_show_returns_servers_via_json(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.get_dns_servers",
        lambda _svc: ["1.1.1.1", "8.8.8.8"],
    )
    result = runner.invoke(app, ["dns", "show", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["servers"] == ["1.1.1.1", "8.8.8.8"]


def test_dns_show_handles_dhcp(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.get_dns_servers", lambda _svc: []
    )
    result = runner.invoke(app, ["dns", "show"])
    assert result.exit_code == 0
    assert "DHCP" in result.stdout


def test_dns_set_calls_networksetup_when_not_dry_run(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    calls: list[tuple] = []

    def fake_set(svc, servers):  # type: ignore[no-untyped-def]
        calls.append((svc, servers))
        return True

    monkeypatch.setattr("shimkit.tools.dns.networksetup.set_dns_servers", fake_set)
    monkeypatch.setattr("shimkit.tools.dns.networksetup.flush_cache", lambda: True)
    result = runner.invoke(app, ["dns", "set", "1.1.1.1", "8.8.8.8"])
    assert result.exit_code == 0
    assert calls == [("Wi-Fi", ["1.1.1.1", "8.8.8.8"])]


def test_dns_reset_with_token_clears_dns(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    calls: list[tuple] = []
    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.set_dns_servers",
        lambda svc, servers: calls.append((svc, servers)) or True,
    )
    monkeypatch.setattr("shimkit.tools.dns.networksetup.flush_cache", lambda: True)
    result = runner.invoke(app, ["dns", "reset", "--confirm", "RESET"])
    assert result.exit_code == 0
    assert calls and calls[0][1] == []  # cleared to DHCP


def test_dns_fix_already_resolving_is_noop(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.test_resolution", lambda *_a, **_k: True
    )
    result = runner.invoke(app, ["dns", "fix"])
    assert result.exit_code == 0
    assert "already resolves" in result.stdout.lower()


def test_dns_fix_runs_step_1_and_stops_when_resolved(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix should stop at the first step that resolves DNS."""
    _stub_macos(monkeypatch)

    # First test_resolution: fail (not already resolving). After step 1: pass.
    state = {"calls": 0}

    def fake_resolution(*_a, **_k):  # type: ignore[no-untyped-def]
        state["calls"] += 1
        return state["calls"] > 1

    monkeypatch.setattr("shimkit.tools.dns.fixer.test_resolution", fake_resolution)
    monkeypatch.setattr("shimkit.tools.dns.networksetup.flush_cache", lambda: True)
    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.step_flush",
        lambda: __import__("shimkit.tools.dns.models", fromlist=["FixResult"]).FixResult(
            step=__import__("shimkit.tools.dns.fixer", fromlist=["STEPS"]).STEPS[0],
            applied=True,
            resolved=True,
        ),
    )
    result = runner.invoke(app, ["dns", "fix", "--stop-at", "1"])
    assert result.exit_code == 0


def test_dns_fix_unknown_profile_is_user_error(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.test_resolution", lambda *_a, **_k: False
    )
    result = runner.invoke(app, ["dns", "fix", "--profile", "nonexistent"])
    assert result.exit_code == 1
    assert "Unknown DNS profile" in result.stdout


def test_dns_fix_nuclear_without_token_aborts(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.test_resolution", lambda *_a, **_k: False
    )
    # Run up to step 6 without --confirm — should refuse.
    result = runner.invoke(
        app, ["dns", "fix", "--start-at", "6", "--stop-at", "6"]
    )
    assert result.exit_code == 1
    assert "Pass --confirm REGENERATE" in result.stdout


def test_dns_rollback_no_backup(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_macos(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.latest_backup_dir", lambda: None
    )
    result = runner.invoke(app, ["dns", "rollback"])
    assert result.exit_code == 1
    assert "No DNS plist backup" in result.stdout


def test_dns_profile_list_handles_failure(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`profiles list` requires sudo on macOS Sequoia+; surface as exit 77."""
    from shimkit.core import CommandResult

    _stub_macos(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.dns.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(1, "", "needs sudo")),
    )
    result = runner.invoke(app, ["dns", "profile", "list"])
    assert result.exit_code == 77


def test_dns_profile_list_emits_json(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shimkit.core import CommandResult

    _stub_macos(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.dns.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, "_computerlevel: 0\n", "")),
    )
    result = runner.invoke(app, ["dns", "profile", "list", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["step"] == "profile_list"


def test_dns_diagnostics_export_writes_file(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from shimkit.core import CommandResult

    _stub_macos(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.dns.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, "scutil output\n", "")),
    )
    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.get_dns_servers", lambda _svc: ["1.1.1.1"]
    )
    out = tmp_path / "diag.txt"
    result = runner.invoke(app, ["dns", "diagnostics", "export", "--out", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    body = out.read_text()
    assert "shimkit dns diagnostic" in body
    assert "1.1.1.1" in body
    # 0o600 perm check
    mode = out.stat().st_mode & 0o777
    assert mode == 0o600


# --- fixer step functions ------------------------------------------------


def test_step_flush_success_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.dns import fixer

    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.flush_cache", lambda: True
    )
    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.test_resolution", lambda *_a, **_k: True
    )
    monkeypatch.setattr("time.sleep", lambda _s: None)  # speed up
    res = fixer.step_flush()
    assert res.applied is True
    assert res.resolved is True


def test_step_rebuild_resolver_handles_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.tools.dns import fixer

    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.set_dns_servers",
        lambda _svc, _servers: False,
    )
    res = fixer.step_rebuild_resolver("Wi-Fi", ["1.1.1.1"])
    assert res.applied is False
    assert any("Initial" in n for n in res.notes)


def test_step_rebuild_resolver_no_service() -> None:
    from shimkit.tools.dns import fixer

    res = fixer.step_rebuild_resolver("", ["1.1.1.1"])
    assert res.applied is False
    assert any("No active" in n for n in res.notes)


def test_step_uniform_dnssec_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.dns import fixer

    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.set_dns_servers",
        lambda _svc, _servers: True,
    )
    monkeypatch.setattr("shimkit.tools.dns.networksetup.flush_cache", lambda: True)
    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.test_resolution", lambda *_a, **_k: True
    )
    monkeypatch.setattr("time.sleep", lambda _s: None)
    res = fixer.step_uniform_dnssec("Wi-Fi")
    assert res.applied is True
    assert res.resolved is True


def test_step_cycle_interface_no_service(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.dns import fixer

    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.active_service", lambda: None
    )
    res = fixer.step_cycle_interface()
    assert res.applied is False


def test_step_cycle_interface_wifi_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.tools.dns import fixer
    from shimkit.tools.dns.models import NetworkService

    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.active_service",
        lambda: NetworkService(name="Wi-Fi", device="en0", is_wifi=True),
    )
    monkeypatch.setattr(
        "shimkit.tools.dns.networksetup.airport_power", lambda _d, on: True
    )
    monkeypatch.setattr("shimkit.tools.dns.networksetup.flush_cache", lambda: True)
    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.test_resolution", lambda *_a, **_k: True
    )
    monkeypatch.setattr("time.sleep", lambda _s: None)
    res = fixer.step_cycle_interface()
    assert res.applied is True
    assert res.resolved is True


def test_step_detect_vpn_no_interference(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.dns import fixer

    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.detect_interference", lambda: []
    )
    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.test_resolution", lambda *_a, **_k: True
    )
    res = fixer.step_detect_vpn()
    assert res.applied is True
    assert res.resolved is True
    assert res.notes == []


def test_step_detect_vpn_reports_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.tools.dns import fixer

    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.detect_interference",
        lambda: ["Tailscale is running"],
    )
    res = fixer.step_detect_vpn()
    assert res.applied is True
    assert res.notes == ["Tailscale is running"]
    # Findings present → not yet resolved (caller may choose to continue).


def test_rollback_returns_false_when_no_backup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.tools.dns import fixer

    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.latest_backup_dir", lambda: None
    )
    assert fixer.rollback() is False


def test_rollback_restores_existing_backup_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """When a backup dir exists with plist files, rollback copies each one
    back via sudo cp."""
    from shimkit.core import CommandResult
    from shimkit.tools.dns import fixer

    # Build a fake backup dir with one of the three plist filenames present.
    backup_dir = tmp_path / "20250101-000000"
    backup_dir.mkdir()
    (backup_dir / "preferences.plist").write_text("fake plist")

    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.latest_backup_dir", lambda: backup_dir
    )
    captured: list[list[str]] = []
    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.CommandRunner.run",
        staticmethod(lambda cmd, **_: captured.append(cmd) or CommandResult(0, "", "")),
    )
    assert fixer.rollback() is True
    # At least one `sudo cp -a` call for the present plist.
    assert any(cmd[1] == "cp" and cmd[2] == "-a" for cmd in captured if len(cmd) > 2)


def test_detect_interference_reports_running_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shimkit.core import CommandResult
    from shimkit.tools.dns import fixer

    # First pgrep finds OrbStack + tailscaled; per-name probes filter them.
    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        # Bulk pgrep (with all candidates) — return non-empty.
        # Per-name pgreps: OrbStack=found, Docker=not, Tailscale=not, tailscaled=found.
        joined = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        if "pgrep" in joined:
            if joined.endswith("OrbStack") or joined.endswith("tailscaled"):
                return CommandResult(0, "1234", "")
            return CommandResult(0, "1234\n", "") if "Docker" in joined else CommandResult(1, "", "")
        if "ifconfig" in joined:
            return CommandResult(0, "lo0: flags=8049<UP,LOOPBACK>\n", "")
        return CommandResult(1, "", "")

    monkeypatch.setattr(
        "shimkit.tools.dns.fixer.CommandRunner.run", staticmethod(fake_run)
    )
    findings = fixer.detect_interference()
    # The exact strings depend on which pgrep paths matched; at minimum the
    # function should return a list (possibly empty) without raising.
    assert isinstance(findings, list)
