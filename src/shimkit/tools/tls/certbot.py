"""Pure argv + volume builders for the certbot container.

No side effects, no I/O — keeps the manager focused on
orchestration and these on the certbot CLI surface. Every
function returns plain Python types so tests can assert against
them without mocking subprocess.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

Method = Literal["webroot", "dns-cloudflare", "dns-route53"]


def request_argv(
    *,
    domains: list[str],
    email: str,
    method: Method,
    webroot_in_container: str = "/webroot",
    credentials_in_container: str = "/credentials/cloudflare.ini",
    propagation_seconds: int = 60,
    staging: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Argv for ``certbot certonly`` (issuance).

    `--non-interactive` + `--agree-tos` are mandatory because the
    container has no stdin. Caller must collect explicit
    user consent (MODERATE prompt) before invoking.

    The ``dns-cloudflare`` method requires a pre-mounted credentials
    file at ``credentials_in_container`` — `dns_cloudflare_api_token
    = <token>` (one line). Cloudflare propagation delays vary; 60s
    is a safe default that the Cloudflare plugin itself recommends.

    The ``dns-route53`` method reads AWS credentials from
    ``~/.aws/credentials`` inside the container (boto3 default).
    No `--dns-route53-credentials` flag exists; the manager mounts
    the user's AWS credentials file at ``/root/.aws/credentials``.
    """
    if not domains:
        raise ValueError("at least one domain is required")
    if method not in {"webroot", "dns-cloudflare", "dns-route53"}:
        raise ValueError(f"unsupported method: {method!r}")

    argv: list[str] = [
        "certonly",
        "--non-interactive",
        "--agree-tos",
        "--email",
        email,
    ]
    if method == "webroot":
        argv.extend(["--webroot", "-w", webroot_in_container])
    elif method == "dns-cloudflare":
        argv.extend(
            [
                "--dns-cloudflare",
                "--dns-cloudflare-credentials",
                credentials_in_container,
                "--dns-cloudflare-propagation-seconds",
                str(propagation_seconds),
            ]
        )
    else:  # dns-route53
        argv.extend(
            [
                "--dns-route53",
                "--dns-route53-propagation-seconds",
                str(propagation_seconds),
            ]
        )
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
    credentials: Path | None = None,
    credentials_mount: Literal["cloudflare", "route53"] = "cloudflare",
) -> dict[str, dict[str, str]]:
    """Build the docker-py `volumes` dict for a certbot container run.

    Mounts the persistent ``etc-letsencrypt`` dir read-write so the
    cert tree survives the one-shot container's exit. When a
    webroot is supplied (issuance / renewal-webroot mode), bind it
    read-only at ``/webroot``. When DNS-01 credentials are supplied,
    bind them read-only at the provider-specific path:

    - ``credentials_mount="cloudflare"`` — the credentials file's
      parent dir is bound at ``/credentials`` (the
      ``--dns-cloudflare-credentials`` flag picks up the file by
      its name under that dir).
    - ``credentials_mount="route53"`` — the credentials file itself
      is bound at ``/root/.aws/credentials`` (boto3's default
      search path). The route53 plugin reads it directly; there's
      no ``--dns-route53-credentials`` flag.

    The credentials file must already have mode 0600 to satisfy
    certbot's strict check.
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
    if credentials is not None:
        if credentials_mount == "route53":
            # boto3 reads ~/.aws/credentials by default; the
            # container's ~ is /root. Mount the file directly so
            # the credentials path inside is exactly that.
            volumes[str(credentials.expanduser())] = {
                "bind": "/root/.aws/credentials",
                "mode": "ro",
            }
        else:
            # Cloudflare: mount the parent dir; certbot reads
            # /credentials/<filename> per the request_argv default.
            volumes[str(credentials.expanduser().parent)] = {
                "bind": "/credentials",
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
