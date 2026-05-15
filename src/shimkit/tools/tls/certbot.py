"""Pure argv + volume builders for the certbot container.

No side effects, no I/O — keeps the manager focused on
orchestration and these on the certbot CLI surface. Every
function returns plain Python types so tests can assert against
them without mocking subprocess.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal


def request_argv(
    *,
    domains: list[str],
    email: str,
    method: Literal["webroot"],
    webroot_in_container: str = "/webroot",
    staging: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Argv for ``certbot certonly`` (issuance).

    `--non-interactive` + `--agree-tos` are mandatory because the
    container has no stdin. Caller must collect explicit
    user consent (MODERATE prompt) before invoking.
    """
    if not domains:
        raise ValueError("at least one domain is required")
    if method != "webroot":
        raise ValueError(f"unsupported method: {method!r}")
    argv: list[str] = [
        "certonly",
        "--non-interactive",
        "--agree-tos",
        "--email",
        email,
        "--webroot",
        "-w",
        webroot_in_container,
    ]
    for d in domains:
        argv.extend(["-d", d])
    if staging:
        argv.append("--staging")
    if dry_run:
        argv.append("--dry-run")
    return argv


def renew_argv(
    *,
    cert_name: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Argv for ``certbot renew`` (renewal).

    With no `cert_name`, certbot renews every cert in
    ``/etc/letsencrypt/live/`` that's within 30 days of expiry —
    the standard Let's Encrypt renewal window.
    """
    argv: list[str] = ["renew", "--non-interactive"]
    if cert_name:
        argv.extend(["--cert-name", cert_name])
    if force:
        argv.append("--force-renewal")
    if dry_run:
        argv.append("--dry-run")
    return argv


def revoke_argv(*, cert_name: str) -> list[str]:
    """Argv for ``certbot revoke``.

    Revocation tells the ACME CA the cert is no longer trusted —
    a separate operation from deleting local files. Pair with
    `certbot delete` (or `tls` deletes the local dir after a
    successful revoke).
    """
    if not cert_name:
        raise ValueError("cert_name is required")
    return [
        "revoke",
        "--non-interactive",
        "--cert-name",
        cert_name,
    ]


def container_volumes(
    *,
    data_dir: Path,
    webroot: Path | None = None,
) -> dict[str, dict[str, str]]:
    """Build the docker-py `volumes` dict for a certbot container run.

    Mounts the persistent ``etc-letsencrypt`` dir read-write so the
    cert tree survives the one-shot container's exit. When a
    webroot is supplied (issuance / renewal-webroot mode), bind it
    read-only at ``/webroot``.
    """
    volumes: dict[str, dict[str, str]] = {
        str((data_dir / "etc-letsencrypt").expanduser()): {
            "bind": "/etc/letsencrypt",
            "mode": "rw",
        },
        str((data_dir / "var-lib-letsencrypt").expanduser()): {
            "bind": "/var/lib/letsencrypt",
            "mode": "rw",
        },
    }
    if webroot is not None:
        volumes[str(webroot.expanduser())] = {
            "bind": "/webroot",
            "mode": "ro",
        }
    return volumes


def live_dir(*, data_dir: Path) -> Path:
    """Convention: ``<data_dir>/etc-letsencrypt/live/`` holds the live
    cert symlinks Let's Encrypt itself manages.
    """
    return (data_dir / "etc-letsencrypt" / "live").expanduser()


def cert_paths(*, data_dir: Path, domain: str) -> tuple[Path, Path]:
    """(fullchain, privkey) on the host — pointers nginx can read."""
    base = live_dir(data_dir=data_dir) / domain
    return base / "fullchain.pem", base / "privkey.pem"
