"""Cross-platform service-manager facade.

Linux: shells out via the existing :class:`Systemd`.
macOS:  shells out via `brew services`.

Used by tools that need to talk to host-installed daemons rather
than container ones — `shimkit db --on-host` is the first
consumer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .command import CommandResult, CommandRunner
from .platform import Platform
from .systemd import Systemd

ServiceState = Literal["running", "stopped", "missing"]


@dataclass(frozen=True)
class HostServiceResult:
    """Combined CommandResult-ish + state, returned by start/stop."""

    ok: bool
    state: ServiceState
    stdout: str = ""
    stderr: str = ""


class HostService:
    """Abstract interface implemented by SystemdHost / BrewServicesHost.

    Tests mock the concrete subclasses directly. Producers ask for an
    implementation via :meth:`detect`; ``None`` means the host has no
    supported service manager.
    """

    @classmethod
    def detect(cls, platform: Platform | None = None) -> HostService | None:
        plat = platform or Platform.detect()
        if plat.is_linux:
            return SystemdHost()
        if plat.is_macos:
            return BrewServicesHost()
        return None

    def state(self, service: str) -> ServiceState:
        raise NotImplementedError

    def start(self, service: str) -> HostServiceResult:
        raise NotImplementedError

    def stop(self, service: str) -> HostServiceResult:
        raise NotImplementedError


class SystemdHost(HostService):
    """Linux: shells out via :class:`Systemd`."""

    def state(self, service: str) -> ServiceState:
        unit = Systemd.state(service if service.endswith(".service") else f"{service}.service")
        if not unit.exists:
            return "missing"
        return "running" if unit.active else "stopped"

    def start(self, service: str) -> HostServiceResult:
        r = Systemd.start(service)
        return _wrap(r, self.state(service))

    def stop(self, service: str) -> HostServiceResult:
        r = Systemd.stop(service)
        return _wrap(r, self.state(service))


class BrewServicesHost(HostService):
    """macOS: shells out via `brew services <action> <name>`."""

    def state(self, service: str) -> ServiceState:
        # `brew services list` output (whitespace columns):
        #   Name      Status     User    File
        #   mysql     started    you     ~/...
        #   postgresql@16 none ...
        r = CommandRunner.run(["brew", "services", "list"])
        if not r.ok:
            return "missing"
        for line in r.stdout.splitlines():
            parts = line.split()
            if not parts or parts[0] != service:
                continue
            status = parts[1] if len(parts) > 1 else "none"
            if status in {"started", "scheduled"}:
                return "running"
            return "stopped"
        return "missing"

    def start(self, service: str) -> HostServiceResult:
        r = CommandRunner.run(["brew", "services", "start", service])
        return _wrap(r, self.state(service))

    def stop(self, service: str) -> HostServiceResult:
        r = CommandRunner.run(["brew", "services", "stop", service])
        return _wrap(r, self.state(service))


def _wrap(r: CommandResult, state: ServiceState) -> HostServiceResult:
    return HostServiceResult(ok=r.ok, state=state, stdout=r.stdout, stderr=r.stderr)
