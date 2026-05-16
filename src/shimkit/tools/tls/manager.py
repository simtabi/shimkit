"""TlsManager -- orchestrator for ``shimkit tls``.

Container-first: every certbot invocation is a one-shot through
:meth:`shimkit.core.DockerEnv.run_oneshot`. The persistent
``/etc/letsencrypt`` directory lives at
``<tools.tls.data_dir>/etc-letsencrypt/`` on the host so renewals
across container restarts find the same account + cert state.

Filesystem layout::

    <data_dir>/
    ├── etc-letsencrypt/      # mounts to /etc/letsencrypt
    │   ├── live/<domain>/    # symlinks to current cert
    │   ├── archive/<domain>/ # numbered history
    │   ├── accounts/
    │   └── renewal/
    └── var-lib-letsencrypt/  # mounts to /var/lib/letsencrypt
"""

from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from shimkit.config import get_config
from shimkit.core import (
    UI,
    CommandRunner,
    DockerEnv,
    Event,
    ExecOutcome,
    emit_json,
    get_logger,
)
from shimkit.core import version as _vc

from . import certbot
from .models import CertInfo

_LOG = get_logger("tls")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69
SCOPE = "tls"


class TlsManager:
    """``TlsManager.create().boot().request(...)`` etc.

    Holds a single DockerEnv handle (the chokepoint for SDK calls)
    and routes each subcommand through a dedicated method.
    """

    def __init__(self) -> None:
        self._env: DockerEnv | None = None

    @classmethod
    def create(cls) -> TlsManager:
        return cls()

    def boot(self, *, force: bool = False) -> TlsManager:
        try:
            _vc.preflight(("docker",), force=force)
        except _vc.VersionViolationError as exc:
            for violation in exc.results:
                if violation.status is _vc.Status.MISSING:
                    UI.error("`docker` is not on PATH.")
                elif violation.status is _vc.Status.OUT_OF_RANGE and violation.tool_version:
                    UI.error(
                        f"docker {violation.tool_version.raw} is below the required "
                        f"min ({violation.constraint.min or '<any>'})."
                    )
                if violation.remediation:
                    UI.dim(f"  → {violation.remediation}")
            sys.exit(EX_UNAVAILABLE)
        self._env = DockerEnv.create().boot()
        # Make sure the on-disk directory tree exists before any
        # container tries to bind-mount over it.
        cfg = get_config().tools.tls
        for sub in ("etc-letsencrypt", "var-lib-letsencrypt"):
            (Path(cfg.data_dir).expanduser() / sub).mkdir(parents=True, exist_ok=True)
        return self

    # ─── request ────────────────────────────────────────────────────

    def request(
        self,
        *,
        domains: list[str],
        email: str | None,
        webroot: Path | None = None,
        credentials: Path | None = None,
        method: Literal["webroot", "dns-cloudflare"] = "webroot",
        staging: bool = False,
        dry_run: bool = False,
        json_out: bool = False,
    ) -> int:
        cfg = get_config().tools.tls
        if not domains:
            UI.error("At least one --domain is required.")
            return EX_FAIL
        for d in domains:
            if not _is_valid_domain(d):
                UI.error(f"Invalid domain: {d!r}.")
                return EX_FAIL
        resolved_email = email or cfg.default_email
        if not resolved_email:
            UI.error(
                "ACME account email is required. Pass --email or set "
                "tools.tls.default_email in your user config."
            )
            return EX_FAIL

        # Per-method preflight.
        if method == "webroot":
            if webroot is None:
                UI.error("--webroot is required for the webroot ACME method.")
                return EX_FAIL
            if not webroot.is_dir():
                UI.error(
                    f"Webroot {webroot} does not exist. Create the directory "
                    "and ensure nginx serves /.well-known/acme-challenge/* "
                    "from it before running."
                )
                return EX_FAIL
        elif method == "dns-cloudflare":
            if credentials is None:
                UI.error(
                    "--credentials is required for dns-cloudflare. Provide a "
                    "file with `dns_cloudflare_api_token = <token>` (mode 0600)."
                )
                return EX_FAIL
            if not credentials.is_file():
                UI.error(f"Credentials file not found: {credentials}")
                return EX_FAIL
            try:
                mode = credentials.stat().st_mode & 0o777
            except OSError as exc:
                UI.error(f"Could not stat {credentials}: {exc}")
                return EX_FAIL
            if mode & 0o077:
                UI.error(
                    f"{credentials} mode is {oct(mode)[2:]}. certbot refuses "
                    "credentials that are group- or world-readable. Run "
                    f"`chmod 600 {credentials}` and retry."
                )
                return EX_FAIL

        argv = certbot.request_argv(
            domains=domains,
            email=resolved_email,
            method=method,
            propagation_seconds=cfg.cloudflare_propagation_seconds,
            staging=staging,
            dry_run=dry_run,
        )
        outcome = self._run_certbot(
            command=argv,
            webroot=webroot,
            credentials=credentials,
            method=method,
            dry_run=False,  # planning lives above; if we got here, run for real
        )
        return self._emit_outcome(
            outcome,
            step="request",
            json_out=json_out,
            extra={
                "domains": domains,
                "method": method,
                "staging": staging,
                "email": resolved_email,
                "primary_domain": domains[0],
            },
        )

    # ─── renew ──────────────────────────────────────────────────────

    def renew(
        self,
        *,
        domain: str | None = None,
        force: bool = False,
        dry_run: bool = False,
        json_out: bool = False,
    ) -> int:
        argv = certbot.renew_argv(
            cert_name=domain,
            force=force,
            dry_run=dry_run,
        )
        outcome = self._run_certbot(command=argv, webroot=None, dry_run=False)
        return self._emit_outcome(
            outcome,
            step="renew",
            json_out=json_out,
            extra={"domain": domain, "force": force, "dry_run": dry_run},
        )

    # ─── revoke ─────────────────────────────────────────────────────

    def revoke(
        self,
        *,
        domain: str,
        dry_run: bool = False,
        json_out: bool = False,
    ) -> int:
        cfg = get_config().tools.tls
        if not domain:
            UI.error("--domain is required for revoke.")
            return EX_FAIL
        live = certbot.live_dir(data_dir=Path(cfg.data_dir)) / domain
        if not live.exists():
            UI.error(f"No cert found at {live}.")
            return EX_FAIL
        argv = certbot.revoke_argv(cert_name=domain)
        if dry_run:
            UI.info(f"--dry-run: would run `certbot {' '.join(argv)}` in container.")
            return EX_OK
        outcome = self._run_certbot(command=argv, webroot=None, dry_run=False)
        return self._emit_outcome(
            outcome, step="revoke", json_out=json_out, extra={"domain": domain}
        )

    # ─── list ───────────────────────────────────────────────────────

    def list_certs(self, *, json_out: bool = False) -> int:
        cfg = get_config().tools.tls
        live = certbot.live_dir(data_dir=Path(cfg.data_dir))
        if not live.exists():
            if json_out:
                emit_json(Event(tool="tls", step="list", status="ok", data={"certs": []}))
            else:
                UI.info("(no certs)")
            return EX_OK
        rows: list[CertInfo] = []
        for child in sorted(live.iterdir()):
            if not child.is_dir():
                continue
            fullchain, privkey = certbot.cert_paths(
                data_dir=Path(cfg.data_dir), domain=child.name
            )
            if not fullchain.exists():
                continue
            expires_at = _read_cert_expiry(fullchain)
            days = _days_until(expires_at) if expires_at else None
            rows.append(
                CertInfo(
                    domain=child.name,
                    fullchain_path=str(fullchain),
                    privkey_path=str(privkey),
                    expires_at=expires_at,
                    days_remaining=days,
                )
            )
        if json_out:
            emit_json(
                Event(
                    tool="tls",
                    step="list",
                    status="ok",
                    data={
                        "certs": [
                            {
                                "domain": r.domain,
                                "fullchain_path": r.fullchain_path,
                                "privkey_path": r.privkey_path,
                                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                                "days_remaining": r.days_remaining,
                                "expiring_soon": r.expiring_soon,
                            }
                            for r in rows
                        ]
                    },
                )
            )
            return EX_OK
        if not rows:
            UI.info("(no certs)")
            return EX_OK
        UI.header(f"TLS certificates ({len(rows)})")
        for r in rows:
            tail = f"  expires {r.expires_at.date()}" if r.expires_at else "  expiry: ?"
            if r.days_remaining is not None:
                tail += f" ({r.days_remaining}d remaining)"
            if r.expiring_soon:
                tail += "  [EXPIRING SOON]"
            UI.line(f"  {r.domain:30s}{tail}")
        return EX_OK

    # ─── status (single cert) ────────────────────────────────────────

    def status(self, *, domain: str, json_out: bool = False) -> int:
        cfg = get_config().tools.tls
        fullchain, privkey = certbot.cert_paths(data_dir=Path(cfg.data_dir), domain=domain)
        if not fullchain.exists():
            UI.error(f"No cert for {domain} at {fullchain}.")
            return EX_FAIL
        expires_at = _read_cert_expiry(fullchain)
        days = _days_until(expires_at) if expires_at else None
        info = CertInfo(
            domain=domain,
            fullchain_path=str(fullchain),
            privkey_path=str(privkey),
            expires_at=expires_at,
            days_remaining=days,
        )
        if json_out:
            emit_json(
                Event(
                    tool="tls",
                    step="status",
                    status="ok",
                    data={
                        "domain": info.domain,
                        "fullchain_path": info.fullchain_path,
                        "privkey_path": info.privkey_path,
                        "expires_at": info.expires_at.isoformat() if info.expires_at else None,
                        "days_remaining": info.days_remaining,
                        "expiring_soon": info.expiring_soon,
                    },
                )
            )
            return EX_OK
        UI.header(f"{domain}")
        UI.line(f"  fullchain: {info.fullchain_path}")
        UI.line(f"  privkey:   {info.privkey_path}")
        if info.expires_at:
            UI.line(f"  expires:   {info.expires_at.date()}  ({info.days_remaining}d)")
        else:
            UI.line("  expires:   ?  (could not parse cert)")
        if info.expiring_soon:
            UI.warning("Cert is within the 30-day renewal window.")
        return EX_OK

    # ─── cron-install ──────────────────────────────────────────────

    def cron_install(self, *, schedule: str | None = None, dry_run: bool = False) -> int:
        cfg = get_config().tools.tls
        entry_schedule = schedule or cfg.renewal_schedule
        # `shimkit tls renew` is its own preflight + safety; the cron
        # entry just shells out to the local binary.
        shimkit_bin = shutil.which("shimkit") or "shimkit"
        command = f"{shimkit_bin} tls renew --yes --json >> /dev/null 2>&1"
        from shimkit.tools.cron.manager import CronManager

        UI.info(f"Installing cron entry 'tls-renew': {entry_schedule}  {command}")
        return (
            CronManager.create()
            .boot()
            .add(
                name="tls-renew",
                schedule=entry_schedule,
                command=command,
                comment="Renew TLS certs via shimkit tls",
                dry_run=dry_run,
            )
        )

    # ─── internals ─────────────────────────────────────────────────

    def _run_certbot(
        self,
        *,
        command: list[str],
        webroot: Path | None = None,
        credentials: Path | None = None,
        method: Literal["webroot", "dns-cloudflare"] = "webroot",
        dry_run: bool,
    ) -> ExecOutcome:
        assert self._env is not None, "call boot() first"
        cfg = get_config().tools.tls
        if dry_run:
            return ExecOutcome(exit_code=0, stdout="(dry-run)\n", stderr="")
        volumes = certbot.container_volumes(
            data_dir=Path(cfg.data_dir),
            webroot=webroot,
            credentials=credentials,
        )
        image = (
            cfg.certbot_dns_cloudflare_image
            if method == "dns-cloudflare"
            else cfg.certbot_image
        )
        return self._env.run_oneshot(
            image,
            command=command,
            labels={"shimkit.tool": SCOPE},
            volumes=volumes,
        )

    def _emit_outcome(
        self,
        outcome: ExecOutcome,
        *,
        step: str,
        json_out: bool,
        extra: dict[str, object] | None = None,
    ) -> int:
        data: dict[str, object] = {
            "exit_code": outcome.exit_code,
            "stdout": outcome.stdout,
            "stderr": outcome.stderr,
        }
        if extra:
            data.update(extra)
        if json_out:
            emit_json(
                Event(
                    tool="tls",
                    step=step,
                    status="ok" if outcome.ok else "error",
                    data=data,
                )
            )
            return EX_OK if outcome.ok else EX_FAIL
        if outcome.stdout:
            UI.line(outcome.stdout.rstrip())
        if outcome.stderr:
            UI.line(outcome.stderr.rstrip())
        if not outcome.ok:
            _LOG.warning("certbot exited %d", outcome.exit_code)
            UI.error(f"certbot exited {outcome.exit_code}.")
            return EX_FAIL
        UI.success(f"{step} ✓")
        return EX_OK


# ─── module helpers ──────────────────────────────────────────────────


def _is_valid_domain(name: str) -> bool:
    """Conservative domain check — letters, digits, dot, hyphen.

    Refuses leading/trailing dots, double-dots, leading hyphens.
    Accepts a single leading ``*.`` for wildcard certs (required by
    DNS-01 mode). Not RFC-perfect (no internationalised names, no
    LDH-exception for first/last char); covers the practical Let's
    Encrypt input space.
    """
    if not name or len(name) > 253:
        return False
    if name.startswith(".") or name.endswith(".") or ".." in name:
        return False
    parts = name.split(".")
    label_re = re.compile(r"^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)$")
    # Wildcard: first label is `*`, rest must validate normally.
    if parts[0] == "*":
        rest = parts[1:]
        return len(rest) >= 2 and all(label_re.match(p) for p in rest)
    return len(parts) >= 2 and all(label_re.match(p) for p in parts)


def _read_cert_expiry(fullchain: Path) -> datetime | None:
    """Use the host's `openssl` to parse the cert's notAfter.

    `openssl x509 -enddate -noout` returns one line:
    ``notAfter=Aug  5 12:34:56 2026 GMT``
    """
    r = CommandRunner.run(
        ["openssl", "x509", "-enddate", "-noout", "-in", str(fullchain)]
    )
    if not r.ok:
        return None
    raw = r.stdout.strip()
    if not raw.startswith("notAfter="):
        return None
    raw = raw.removeprefix("notAfter=")
    # OpenSSL format example: "Aug  5 12:34:56 2026 GMT"
    try:
        return datetime.strptime(raw, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _days_until(when: datetime) -> int:
    return (when - datetime.now(tz=timezone.utc)).days
