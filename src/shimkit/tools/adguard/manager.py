"""AdGuardManager — orchestrator for ``shimkit adguard``."""

from __future__ import annotations

import shutil
import socket
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal

from shimkit.config import get_config
from shimkit.core import (
    UI,
    CommandRunner,
    Event,
    Menu,
    Platform,
    Systemd,
    emit_json,
    get_logger,
    has_sudo_cached,
    sudo_prefix,
)

from . import api, finder, ports, resolv, yaml_editor
from .models import AdGuardInstall, FixOutcome, PortConflict

_LOG = get_logger("adguard")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69
EX_NOPERM = 77


def _require_optional_extras() -> bool:
    """Refuse to proceed when the ``adguard`` extra isn't installed."""
    missing: list[str] = []
    for name, mod in (("psutil", "psutil"), ("requests", "requests"), ("ruamel.yaml", "ruamel.yaml")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(name)
    if missing:
        UI.error(
            f"shimkit adguard needs optional extras: {', '.join(missing)}.\n"
            "  Install with:  uv tool install 'shimkit[extra-tools]'\n"
            "  or:            pipx inject shimkit ruamel.yaml requests psutil"
        )
        return False
    return True


class AdGuardManager:
    def __init__(self) -> None:
        self._platform: Platform | None = None
        self._install: AdGuardInstall | None = None

    @classmethod
    def create(cls) -> AdGuardManager:
        return cls()

    def boot(
        self,
        *,
        install_override: Path | None = None,
        require_install: bool = True,
        require_root: bool = False,
    ) -> AdGuardManager:
        self._platform = Platform.detect()
        if not self._platform.is_linux:
            UI.error(
                "shimkit adguard targets Linux. "
                f"Detected platform: {self._platform.system}."
            )
            sys.exit(EX_UNAVAILABLE)
        if not _require_optional_extras():
            sys.exit(EX_UNAVAILABLE)
        if require_root and not has_sudo_cached():
            UI.error(
                "This action writes to /etc/* and controls systemd units. "
                "Re-run with sudo or refresh your sudo timestamp first."
            )
            sys.exit(EX_NOPERM)
        self._install = finder.detect(install_override)
        if self._install is None and require_install:
            UI.error(
                "AdGuard Home install not found. Install AGH first, or pass "
                "--install /opt/AdGuardHome to override."
            )
            sys.exit(EX_UNAVAILABLE)
        return self

    # ---- helpers ---------------------------------------------------------

    def _configured_ports(self) -> tuple[int, int]:
        """Return ``(dns_port, http_port)`` from yaml, falling back to defaults."""
        if self._install and self._install.yaml_path:
            dns_p, http_p = yaml_editor.read_ports(self._install.yaml_path)
            return (dns_p or 53, http_p or 80)
        return (53, 80)

    def _scan(self) -> list[PortConflict]:
        cfg = get_config().tools.adguard
        dns_p, http_p = self._configured_ports()
        target_ports: list[tuple[int, Literal["tcp", "udp"], str]] = []
        for tp in cfg.target_ports:
            port = tp.port
            if port == 53:
                port = dns_p
            elif port == 80:
                port = http_p
            target_ports.append((port, tp.proto, tp.role))
        # Dedupe while preserving order.
        seen: set[tuple[int, str]] = set()
        deduped: list[tuple[int, Literal["tcp", "udp"], str]] = []
        for port, proto, role in target_ports:
            if (port, proto) in seen:
                continue
            seen.add((port, proto))
            deduped.append((port, proto, role))

        conflicts: list[PortConflict] = []
        for port, proto, role in deduped:
            for owner in ports.owners_of(port, proto):
                if ports.is_agh_process(owner.name):
                    continue
                conflicts.append(
                    PortConflict(port=port, proto=proto, role=role, owner=owner)
                )
        return conflicts

    # ---- read-only commands ---------------------------------------------

    def scan(self, *, json_out: bool = False) -> int:
        dns_p, http_p = self._configured_ports()
        conflicts = self._scan()
        if json_out:
            emit_json(
                Event(
                    tool="adguard",
                    step="scan",
                    status="warning" if conflicts else "ok",
                    message=f"{len(conflicts)} conflict(s)",
                    data={
                        "dns_port": dns_p,
                        "http_port": http_p,
                        "install": str(self._install.binary) if self._install else None,
                        "yaml": str(self._install.yaml_path) if self._install and self._install.yaml_path else None,
                        "conflicts": [
                            {
                                "port": c.port,
                                "proto": c.proto,
                                "role": c.role,
                                "owner": {
                                    "pid": c.owner.pid,
                                    "name": c.owner.name,
                                    "unit": c.owner.unit,
                                },
                            }
                            for c in conflicts
                        ],
                    },
                )
            )
            return EX_OK
        UI.header("AdGuard Home scan")
        if self._install:
            UI.line(f"  install : {self._install.install_root}")
            UI.line(f"  yaml    : {self._install.yaml_path or '<not yet generated>'}")
        UI.line(f"  ports   : dns={dns_p}  http={http_p}")
        if not conflicts:
            UI.success("  No conflicts on AGH target ports.")
            return EX_OK
        UI.warning(f"  {len(conflicts)} conflict(s):")
        for c in conflicts:
            UI.warning(
                f"    {c.proto}/{c.port} ({c.role}) held by "
                f"{c.owner.name} pid={c.owner.pid} unit={c.owner.unit or '?'}"
            )
        return EX_OK

    def verify(self, *, json_out: bool = False, timeout: float = 5.0) -> int:
        dns_p, _ = self._configured_ports()
        api_status = api.status(timeout=timeout)
        dns_ok = self._loopback_dns_test(dns_p, timeout=timeout)
        ok = bool(api_status) and dns_ok
        if json_out:
            emit_json(
                Event(
                    tool="adguard",
                    step="verify",
                    status="ok" if ok else "error",
                    message="reachable" if ok else "unreachable",
                    data={"api": bool(api_status), "loopback_dns": dns_ok, "dns_port": dns_p},
                )
            )
            return EX_OK if ok else EX_FAIL
        UI.header("AdGuard Home verify")
        UI.line(f"  Control API : {'OK' if api_status else 'FAIL'}")
        UI.line(f"  Loopback DNS: {'OK' if dns_ok else 'FAIL'} (127.0.0.1:{dns_p})")
        return EX_OK if ok else EX_FAIL

    def _loopback_dns_test(self, port: int, timeout: float = 3.0) -> bool:
        """Best-effort DNS query against 127.0.0.1:<port>.

        Uses ``dnspython`` when available, otherwise falls back to a
        TCP connect on the port (less precise but always available).
        """
        try:
            import dns.resolver

            r = dns.resolver.Resolver(configure=False)
            r.nameservers = ["127.0.0.1"]
            r.port = port
            r.lifetime = timeout
            try:
                r.resolve("example.org", "A")
                return True
            except Exception:
                return False
        except ImportError:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=timeout):
                    return True
            except OSError:
                return False

    def ports_show(self, *, json_out: bool = False) -> int:
        if self._install is None or self._install.yaml_path is None:
            UI.error("No AGH yaml present yet (first-run not completed?).")
            return EX_UNAVAILABLE
        dns_p, http_p = yaml_editor.read_ports(self._install.yaml_path)
        if json_out:
            emit_json(
                Event(
                    tool="adguard",
                    step="ports_show",
                    status="ok",
                    data={"dns_port": dns_p, "http_port": http_p},
                )
            )
            return EX_OK
        UI.line(f"dns.port  : {dns_p}")
        UI.line(f"http.port : {http_p}")
        return EX_OK

    def ports_set(self, *, dns: int, http: int, dry_run: bool = False) -> int:
        if self._install is None or self._install.yaml_path is None:
            UI.error("No AGH yaml present; cannot set ports.")
            return EX_UNAVAILABLE
        cfg = get_config().tools.adguard

        if dry_run:
            UI.info(f"[dry-run] Would set dns.port={dns}, http.port={http}.")
            return EX_OK

        # Prefer API when AGH is running and reachable.
        if cfg.prefer_api_over_yaml and api.is_reachable(timeout=3.0):
            UI.info("Using AGH control API (no yaml race).")
            if api.set_ports(dns_port=dns, http_port=http):
                UI.success(f"Ports set: dns={dns}, http={http}.")
                return EX_OK
            UI.warning("API call failed — falling back to yaml edit.")

        # YAML path: stop AGH first so its shutdown doesn't overwrite our edit.
        UI.info("Stopping AdGuardHome before editing yaml…")
        Systemd.stop("AdGuardHome")
        backup = self._install.yaml_path.with_suffix(
            self._install.yaml_path.suffix + f".bak-{datetime.now():%Y%m%d%H%M%S}"
        )
        shutil.copy2(self._install.yaml_path, backup)
        UI.dim(f"  yaml backup: {backup}")
        try:
            new_dns, new_http = yaml_editor.set_ports(
                self._install.yaml_path, dns=dns, http=http
            )
        except Exception as exc:
            UI.error(f"YAML edit failed: {exc}")
            Systemd.start("AdGuardHome")
            return EX_FAIL
        UI.success(f"YAML updated: dns={new_dns}, http={new_http}.")
        Systemd.start("AdGuardHome")
        return EX_OK

    def config_validate(self) -> int:
        if self._install is None:
            UI.error("AGH binary not found.")
            return EX_UNAVAILABLE
        r = CommandRunner.run([str(self._install.binary), "--check-config"])
        if r.ok:
            UI.success("AGH config valid.")
            return EX_OK
        UI.error(r.stderr or r.stdout or "AGH --check-config reported errors.")
        return EX_FAIL

    def service(self, action: str) -> int:
        action = action.lower()
        cmd_map = {
            "start": Systemd.start,
            "stop": Systemd.stop,
            "restart": Systemd.restart,
        }
        if action == "status":
            state = Systemd.state("AdGuardHome")
            UI.line(
                f"active={state.active}  enabled={state.enabled}  exists={state.exists}"
            )
            return EX_OK if state.active else EX_FAIL
        fn = cmd_map.get(action)
        if fn is None:
            UI.error(f"Unknown service action: {action}")
            return EX_FAIL
        r = fn("AdGuardHome")
        return EX_OK if r.ok else EX_FAIL

    def logs(self, *, lines: int = 80, follow: bool = False) -> int:
        Systemd.journal("AdGuardHome", lines=lines, follow=follow)
        return EX_OK

    def rollback(self) -> int:
        # Restore yaml from the most recent shimkit-managed backup, AND
        # restore resolv.conf from the most recent /etc backup.
        restored_any = False
        if self._install and self._install.yaml_path:
            backups = sorted(self._install.yaml_path.parent.glob(
                f"{self._install.yaml_path.name}.bak-*"
            ))
            if backups:
                shutil.copy2(backups[-1], self._install.yaml_path)
                UI.success(f"Restored yaml from {backups[-1]}.")
                restored_any = True
        rb = resolv.latest_resolv_backup()
        if rb:
            CommandRunner.run(
                [*sudo_prefix(), "cp", "-a", str(rb), "/etc/resolv.conf"],
                capture_output=False,
            )
            UI.success(f"Restored /etc/resolv.conf from {rb}.")
            restored_any = True
        if not restored_any:
            UI.warning("Nothing to roll back.")
            return EX_FAIL
        return EX_OK

    def fix(
        self,
        *,
        dry_run: bool = False,
        remap_only: bool = False,
        dns_cleanup_only: bool = False,
        migrate_from_pihole: bool = False,
        json_out: bool = False,
    ) -> int:
        cfg = get_config().tools.adguard
        outcomes: list[FixOutcome] = []
        conflicts = self._scan()

        # Phase: handle systemd-resolved + NetworkManager.
        if not remap_only and resolv.is_resolved_active():
            o = FixOutcome(step="resolved")
            if dry_run:
                o.notes.append("Would write DNSStubListener=no drop-in.")
                o.notes.append("Would rewrite /etc/resolv.conf.")
                if resolv.is_nm_active():
                    o.notes.append("Would write NetworkManager dns=none drop-in.")
            else:
                resolv.disable_resolved_stub()
                o.notes.append("systemd-resolved stub disabled.")

                resolv_ok = (
                    resolv.write_resolv_static()
                    if cfg.resolv_conf_mode == "static"
                    else resolv.write_resolv_symlink()
                )
                if resolv_ok:
                    o.notes.append(
                        f"/etc/resolv.conf rewritten ({cfg.resolv_conf_mode})."
                    )
                else:
                    o.error = (
                        "Could not rewrite /etc/resolv.conf "
                        "(bind-mounted or insufficient privilege?)."
                    )

                nm_applied = resolv.configure_network_manager()
                if nm_applied:
                    o.notes.append("NetworkManager dns=none drop-in written.")
                elif resolv.is_nm_active():
                    o.notes.append(
                        "NetworkManager is active but the drop-in write failed."
                    )
                # else: NM inactive, nothing to do — no note.

                o.applied = (o.error is None)
            outcomes.append(o)

        # Phase: known-safe units. dnsmasq/bind9/named/unbound get stopped.
        # pi-hole requires --migrate-from-pihole.
        for c in conflicts:
            unit = c.owner.unit or ""
            if unit in cfg.safe_units_to_stop:
                o = FixOutcome(step=f"stop:{unit}")
                if dry_run:
                    o.notes.append(f"Would stop+disable {unit}.")
                else:
                    Systemd.stop(unit)
                    Systemd.disable(unit)
                    o.applied = True
                    o.notes.append(f"Stopped and disabled {unit}.")
                outcomes.append(o)
            elif unit == cfg.pihole_unit and migrate_from_pihole:
                o = FixOutcome(step=f"stop:{unit}")
                if not dry_run:
                    Systemd.stop(unit)
                    Systemd.disable(unit)
                    o.applied = True
                outcomes.append(o)
            elif unit == cfg.pihole_unit:
                o = FixOutcome(step=f"skip:{unit}")
                o.notes.append("pi-hole is the conflict — pass --migrate-from-pihole to stop it.")
                outcomes.append(o)

        if dns_cleanup_only:
            return self._emit_outcomes(outcomes, json_out=json_out)

        # Re-scan; remap yaml if still blocked on dns/http.
        time.sleep(2 if not dry_run else 0)
        still = self._scan()
        dns_p, http_p = self._configured_ports()
        dns_blocked = any(c.port == dns_p for c in still)
        http_blocked = any(c.port == http_p for c in still)
        if (dns_blocked or http_blocked) and self._install and self._install.yaml_path:
            o = FixOutcome(step="yaml_remap")
            new_dns = cfg.default_remap_dns_port if dns_blocked else dns_p
            new_http = cfg.default_remap_http_port if http_blocked else http_p
            if dry_run:
                o.notes.append(f"Would set dns.port={new_dns}, http.port={new_http}.")
            else:
                code = self.ports_set(dns=new_dns, http=new_http)
                o.applied = code == EX_OK
            outcomes.append(o)

        # Finally restart AGH.
        if not dry_run:
            Systemd.restart("AdGuardHome")
            outcomes.append(FixOutcome(step="restart", applied=True))

        return self._emit_outcomes(outcomes, json_out=json_out)

    def _emit_outcomes(
        self, outcomes: list[FixOutcome], *, json_out: bool
    ) -> int:
        if json_out:
            emit_json(
                [
                    Event(
                        tool="adguard",
                        step=o.step,
                        status="ok" if o.applied else "warning",
                        message=", ".join(o.notes) if o.notes else "",
                        data={"applied": o.applied, "notes": o.notes},
                    )
                    for o in outcomes
                ]
            )
        else:
            for o in outcomes:
                if o.applied:
                    UI.success(f"  {o.step}")
                else:
                    UI.warning(f"  {o.step}")
                for n in o.notes:
                    UI.dim(f"    {n}")
        return EX_OK

    # ---- interactive menu ----------------------------------------------

    def run(self) -> None:
        actions: list[tuple[str, Callable[[], object]]] = [
            ("Scan (read-only)", lambda: self.scan()),
            ("Fix (remediate)", lambda: self.fix()),
            ("Verify", lambda: self.verify()),
            ("Show configured ports", lambda: self.ports_show()),
            ("Service status", lambda: self.service("status")),
            ("Tail journal logs", lambda: self.logs(lines=40)),
            ("Exit", lambda: None),
        ]
        labels = [lbl for lbl, _ in actions]
        dispatch = dict(actions)
        while True:
            choice = Menu.select("AdGuard — what would you like to do?", labels)
            if choice is None or choice == "Exit":
                UI.info("Goodbye!")
                return
            handler = dispatch.get(choice)
            if handler:
                handler()
