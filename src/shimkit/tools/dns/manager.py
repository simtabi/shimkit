"""DnsManager — orchestrator for the macOS DNS recovery tool."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

from shimkit.config import get_config
from shimkit.core import UI, CommandRunner, Event, Menu, Platform, emit_json, get_logger

from . import fixer, networksetup, scutil
from .models import FixResult, NetworkService

_LOG = get_logger("dns")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69
EX_NOPERM = 77


class DnsManager:
    """Orchestrator. Boot detects platform; run() is the menu loop."""

    def __init__(self) -> None:
        self._platform: Platform | None = None
        self._service: NetworkService | None = None

    @classmethod
    def create(cls) -> DnsManager:
        return cls()

    def boot(self) -> DnsManager:
        self._platform = Platform.detect()
        if not self._platform.is_macos:
            UI.error(
                "shimkit dns targets macOS. "
                f"Detected platform: {self._platform.system}."
            )
            sys.exit(EX_UNAVAILABLE)
        self._service = networksetup.active_service()
        if self._service is None:
            UI.warning(
                "Could not detect the active network service — "
                "some commands will be unavailable until network comes up."
            )
        return self

    # ---- read-only commands ----------------------------------------------

    def diagnose(self, *, json_out: bool = False) -> int:
        chain = scutil.query()
        interference = fixer.detect_interference()
        service = self._service

        if json_out:
            data: dict[str, object] = {
                "resolvers": [
                    {
                        "index": r.index,
                        "nameservers": list(r.nameservers),
                        "search_domains": list(r.search_domains),
                        "interface": r.interface,
                        "flags": r.flags,
                    }
                    for r in chain.resolvers
                ],
                "active_service": (
                    {"name": service.name, "device": service.device, "wifi": service.is_wifi}
                    if service
                    else None
                ),
                "interference": interference,
            }
            emit_json(
                Event(
                    tool="dns",
                    step="diagnose",
                    status="ok",
                    message=f"{len(chain.resolvers)} resolver(s)",
                    data=data,
                )
            )
            return EX_OK

        UI.header("DNS Diagnostic")
        if service:
            UI.line(f"  Active service : {service.name} ({service.device})")
            UI.line(f"  Wi-Fi          : {service.is_wifi}")
        else:
            UI.warning("  No active service detected.")
        UI.line(f"  Resolvers      : {len(chain.resolvers)}")
        for r in chain.resolvers:
            UI.line(f"    [#{r.index}] {','.join(r.nameservers) or '(none)'} "
                    f"if={r.interface or '-'} flags={r.flags or '-'}")
            if r.is_tailscale:
                UI.warning("      ↑ Tailscale MagicDNS (100.100.100.100) present")
        if interference:
            UI.warning("  Potential interference:")
            for note in interference:
                UI.warning(f"    - {note}")
        else:
            UI.success("  No Docker/Tailscale/VPN interference detected.")
        return EX_OK

    def flush(self, *, json_out: bool = False) -> int:
        ok = networksetup.flush_cache()
        if json_out:
            emit_json(
                Event(
                    tool="dns",
                    step="flush",
                    status="ok" if ok else "error",
                    message="dscacheutil flushed + mDNSResponder HUP'd"
                    if ok
                    else "Flush command failed (sudo required?)",
                )
            )
        else:
            if ok:
                UI.success("DNS cache flushed.")
            else:
                UI.error("Flush failed — sudo required?")
        return EX_OK if ok else EX_NOPERM

    def show(self, service: str | None = None, *, json_out: bool = False) -> int:
        svc = service or (self._service.name if self._service else None)
        if not svc:
            UI.error("No service specified and none auto-detected.")
            return EX_FAIL
        servers = networksetup.get_dns_servers(svc)
        if json_out:
            emit_json(
                Event(
                    tool="dns",
                    step="show",
                    status="ok",
                    message=f"{len(servers)} server(s)",
                    data={"service": svc, "servers": servers},
                )
            )
        else:
            UI.line(f"service: {svc}")
            if servers:
                for s in servers:
                    UI.line(f"  - {s}")
            else:
                UI.line("  <using DHCP>")
        return EX_OK

    def test(self, domains: list[str], *, json_out: bool = False) -> int:
        if not domains:
            domains = list(get_config().tools.dns.test_domains)
        results: dict[str, bool] = {}
        for d in domains:
            results[d] = fixer.test_resolution(d, timeout=3.0)
        passed = all(results.values())
        if json_out:
            emit_json(
                Event(
                    tool="dns",
                    step="test",
                    status="ok" if passed else "error",
                    message=f"{sum(results.values())}/{len(results)} resolved",
                    data={"results": results},
                )
            )
        else:
            UI.header("DNS resolution test")
            for d, ok in results.items():
                if ok:
                    UI.success(f"  {d}")
                else:
                    UI.error(f"  {d}")
        return EX_OK if passed else EX_FAIL

    def profile_list(self, *, json_out: bool = False) -> int:
        """List installed configuration profiles (encrypted-DNS, etc.)."""
        r = CommandRunner.run(["profiles", "list"])
        if not r.ok:
            UI.error("`profiles list` failed (requires sudo on some systems).")
            return EX_NOPERM
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        if json_out:
            emit_json(
                Event(
                    tool="dns",
                    step="profile_list",
                    status="ok",
                    message=f"{len(lines)} line(s)",
                    data={"raw": lines},
                )
            )
            return EX_OK
        UI.header("Installed configuration profiles")
        if not lines:
            UI.info("  (none)")
        else:
            for line in lines:
                UI.line(f"  {line}")
        return EX_OK

    # ---- mutating commands -----------------------------------------------

    def set_servers(
        self,
        servers: list[str],
        *,
        service: str | None = None,
        dry_run: bool = False,
    ) -> int:
        svc = service or (self._service.name if self._service else None)
        if not svc:
            UI.error("No service specified and none auto-detected.")
            return EX_FAIL
        if dry_run:
            UI.info(f"[dry-run] Would set DNS for {svc} to {', '.join(servers)}.")
            return EX_OK
        if not networksetup.set_dns_servers(svc, servers):
            UI.error("Failed to set DNS servers.")
            return EX_NOPERM
        networksetup.flush_cache()
        UI.success(f"DNS for {svc} set to {', '.join(servers)}.")
        return EX_OK

    def reset(self, *, confirm: str | None, service: str | None = None) -> int:
        svc = service or (self._service.name if self._service else None)
        if not svc:
            UI.error("No service specified and none auto-detected.")
            return EX_FAIL
        token = get_config().tools.dns.reset_confirm_token
        if confirm != token:
            UI.error(f"Severe action. Pass --confirm {token} to proceed.")
            return EX_FAIL
        if not networksetup.set_dns_servers(svc, []):
            UI.error("Reset failed.")
            return EX_NOPERM
        networksetup.flush_cache()
        UI.success(f"DNS for {svc} reset to DHCP.")
        return EX_OK

    def fix(
        self,
        *,
        start_at: int = 1,
        stop_at: int = 6,
        skip_nuclear: bool = False,
        profile: str = "cloudflare",
        nuclear_confirm: str | None = None,
        json_out: bool = False,
    ) -> int:
        """Run the 6-step escalation. Stops at the first step that fixes resolution."""
        cfg = get_config().tools.dns
        if profile not in cfg.dns_servers:
            UI.error(
                f"Unknown DNS profile: {profile}. "
                f"Available: {', '.join(cfg.dns_servers)}"
            )
            return EX_FAIL
        servers = cfg.dns_servers[profile]
        service = self._service
        if service is None:
            UI.error("No active service. Bring the network up and retry.")
            return EX_UNAVAILABLE

        results: list[FixResult] = []
        if fixer.test_resolution("google.com"):
            UI.success("DNS already resolves. Nothing to fix.")
            if json_out:
                emit_json(Event(tool="dns", step="fix", status="ok", message="no-op"))
            return EX_OK

        for step in fixer.STEPS:
            if step.number < start_at or step.number > stop_at:
                continue
            if step.number == 6:
                if skip_nuclear:
                    UI.info("Skipping nuclear step (--skip-nuclear).")
                    continue
                token = cfg.nuclear_confirm_token
                if nuclear_confirm != token:
                    UI.error(
                        f"Step 6 is destructive. Pass --confirm {token} to proceed."
                    )
                    return EX_FAIL

            UI.header(f"Step {step.number}/6 — {step.description}")
            if step.number == 1:
                res = fixer.step_flush()
            elif step.number == 2:
                res = fixer.step_rebuild_resolver(service.name, servers)
            elif step.number == 3:
                res = fixer.step_uniform_dnssec(service.name)
            elif step.number == 4:
                res = fixer.step_cycle_interface()
            elif step.number == 5:
                res = fixer.step_detect_vpn()
            else:
                res = fixer.step_nuclear()
            results.append(res)
            for note in res.notes:
                UI.dim(f"    {note}")
            if res.resolved:
                UI.success(f"Step {step.number} resolved the issue.")
                break
            else:
                UI.warning(f"Step {step.number} did not resolve.")

        resolved = bool(results and results[-1].resolved)
        if json_out:
            emit_json(
                [
                    Event(
                        tool="dns",
                        step=r.step.name,
                        status="ok" if r.resolved else ("warning" if r.applied else "error"),
                        message="resolved" if r.resolved else "did not resolve",
                        data={"notes": r.notes},
                    )
                    for r in results
                ]
            )
        return EX_OK if resolved else EX_FAIL

    def rollback(self) -> int:
        backup = fixer.latest_backup_dir()
        if not backup:
            UI.error("No DNS plist backup found.")
            return EX_FAIL
        UI.info(f"Restoring from {backup}")
        if fixer.rollback():
            UI.success("Restored. Reboot or log out to fully reload SystemConfiguration.")
            return EX_OK
        UI.error("Rollback failed.")
        return EX_FAIL

    def diagnostics_export(self, out: Path | None) -> int:
        """Write a diagnostic bundle to ``out`` (or backup_dir/diagnostics-...txt)."""
        if out is None:
            base = Path(get_config().tools.dns.backup_dir).expanduser()
            base.mkdir(parents=True, exist_ok=True)
            from datetime import datetime

            out = base / f"diagnostics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"

        scutil_out = CommandRunner.run(["scutil", "--dns"]).stdout
        ifconfig = CommandRunner.run(["ifconfig"]).stdout
        service = self._service.name if self._service else "(unknown)"
        servers = networksetup.get_dns_servers(service) if self._service else []

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            "\n".join(
                [
                    f"shimkit dns diagnostic — {service}",
                    f"servers: {', '.join(servers) or '(DHCP)'}",
                    "",
                    "--- scutil --dns ---",
                    scutil_out,
                    "",
                    "--- ifconfig ---",
                    ifconfig,
                ]
            ),
            encoding="utf-8",
        )
        os.chmod(out, 0o600)
        UI.success(f"Diagnostics written to {out}")
        return EX_OK

    # ---- interactive menu -------------------------------------------------

    def run(self) -> None:
        actions: list[tuple[str, Callable[[], object]]] = [
            ("Diagnose (read-only)", lambda: self.diagnose()),
            ("Flush DNS cache", lambda: self.flush()),
            ("Test resolution", lambda: self.test([])),
            ("Show configured DNS", lambda: self.show()),
            ("Profile list (encrypted DNS)", lambda: self.profile_list()),
            ("Exit", lambda: None),
        ]
        labels = [lbl for lbl, _ in actions]
        dispatch = dict(actions)
        while True:
            choice = Menu.select("DNS — what would you like to do?", labels)
            if choice is None or choice == "Exit":
                UI.info("Goodbye!")
                return
            handler = dispatch.get(choice)
            if handler:
                handler()
