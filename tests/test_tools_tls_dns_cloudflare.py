"""Tests for the v0.13.0 DNS-01 (Cloudflare) addition to shimkit tls.

The existing webroot-flow tests live in test_tools_tls.py; this file
covers the new --method dns-cloudflare path:

- request_argv shape (--dns-cloudflare + credentials path +
  propagation-seconds)
- container_volumes (credentials parent dir mounted at /credentials)
- manager validates --credentials presence + mode 0600
- manager picks the certbot/dns-cloudflare image
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import ExecOutcome
from shimkit.core.platform import Platform
from shimkit.tools.tls import certbot


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── pure argv builders ─────────────────────────────────────────────────


def test_request_argv_dns_cloudflare_shape() -> None:
    argv = certbot.request_argv(
        domains=["example.com", "*.example.com"],
        email="ops@example.com",
        method="dns-cloudflare",
    )
    assert "--dns-cloudflare" in argv
    assert "--dns-cloudflare-credentials" in argv
    assert "/credentials/cloudflare.ini" in argv
    assert "--dns-cloudflare-propagation-seconds" in argv
    # Default propagation is 60 seconds.
    idx = argv.index("--dns-cloudflare-propagation-seconds")
    assert argv[idx + 1] == "60"
    # Both domains present.
    assert "example.com" in argv
    assert "*.example.com" in argv
    # No webroot flags in DNS mode.
    assert "--webroot" not in argv
    assert "-w" not in argv


def test_request_argv_dns_cloudflare_custom_propagation() -> None:
    argv = certbot.request_argv(
        domains=["example.com"],
        email="ops@example.com",
        method="dns-cloudflare",
        propagation_seconds=120,
    )
    idx = argv.index("--dns-cloudflare-propagation-seconds")
    assert argv[idx + 1] == "120"


def test_request_argv_dns_cloudflare_staging_and_dry_run() -> None:
    argv = certbot.request_argv(
        domains=["example.com"],
        email="ops@example.com",
        method="dns-cloudflare",
        staging=True,
        dry_run=True,
    )
    assert "--staging" in argv
    assert "--dry-run" in argv


def test_request_argv_webroot_unchanged_by_dns_addition() -> None:
    """Adding the DNS path didn't break the webroot path."""
    argv = certbot.request_argv(
        domains=["example.com"],
        email="ops@example.com",
        method="webroot",
    )
    assert "--webroot" in argv
    assert "-w" in argv and "/webroot" in argv
    assert "--dns-cloudflare" not in argv


def test_request_argv_rejects_unknown_method() -> None:
    # `dns-digitalocean` is not yet wired (v0.17.0 only adds
    # cloudflare + route53). Other providers fail the method gate.
    with pytest.raises(ValueError):
        certbot.request_argv(
            domains=["a.com"],
            email="o@a.com",
            method="dns-digitalocean",  # type: ignore[arg-type]
        )


# ─── container_volumes ──────────────────────────────────────────────────


def test_container_volumes_with_credentials(tmp_path: Path) -> None:
    creds = tmp_path / "secrets" / "cloudflare.ini"
    creds.parent.mkdir()
    creds.write_text("dns_cloudflare_api_token = token123\n")
    vols = certbot.container_volumes(data_dir=tmp_path, credentials=creds)
    # Parent dir of the credentials file is mounted at /credentials.
    assert str(creds.parent) in vols
    assert vols[str(creds.parent)]["bind"] == "/credentials"
    assert vols[str(creds.parent)]["mode"] == "ro"
    # And the standard etc-letsencrypt + var-lib-letsencrypt mounts.
    bind_points = {v["bind"] for v in vols.values()}
    assert "/etc/letsencrypt" in bind_points
    assert "/var/lib/letsencrypt" in bind_points


def test_container_volumes_without_credentials_omits_mount(
    tmp_path: Path,
) -> None:
    vols = certbot.container_volumes(data_dir=tmp_path)
    bind_points = {v["bind"] for v in vols.values()}
    assert "/credentials" not in bind_points


# ─── manager: credentials validation ───────────────────────────────────


class _FakeDockerEnv:
    """Mock DockerEnv that records run_oneshot calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    @classmethod
    def create(cls) -> _FakeDockerEnv:
        return cls()

    def boot(self) -> _FakeDockerEnv:
        return self

    def run_oneshot(self, image: str, **kwargs: object) -> ExecOutcome:
        self.calls.append({"image": image, **kwargs})
        return ExecOutcome(exit_code=0, stdout="ok", stderr="")


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch) -> _FakeDockerEnv:
    inst = _FakeDockerEnv()

    class _Factory:
        @classmethod
        def create(cls) -> _FakeDockerEnv:
            return inst

    monkeypatch.setattr("shimkit.tools.tls.manager.DockerEnv", _Factory)
    return inst


@pytest.fixture(autouse=True)
def _autouse(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.tools.tls.manager._vc.preflight", lambda *a, **kw: None)
    monkeypatch.setenv("HOME", str(tmp_path))
    from shimkit.config import reset_cache

    reset_cache()


def _make_creds(tmp_path: Path, *, mode: int = 0o600) -> Path:
    creds_dir = tmp_path / "secrets"
    creds_dir.mkdir(exist_ok=True)
    creds = creds_dir / "cloudflare.ini"
    creds.write_text("dns_cloudflare_api_token = token123\n")
    creds.chmod(mode)
    return creds


def test_dns_cloudflare_requires_credentials(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, fake_env: _FakeDockerEnv
) -> None:
    result = runner.invoke(
        app,
        [
            "tls",
            "request",
            "--yes",
            "-d",
            "example.com",
            "--email",
            "ops@example.com",
            "--method",
            "dns-cloudflare",
        ],
    )
    assert result.exit_code == 1
    assert "credentials" in result.output.lower()


def test_dns_cloudflare_rejects_missing_creds_file(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    fake_env: _FakeDockerEnv,
    tmp_path: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "tls",
            "request",
            "--yes",
            "-d",
            "example.com",
            "--email",
            "ops@example.com",
            "--method",
            "dns-cloudflare",
            "--credentials",
            str(tmp_path / "absent.ini"),
        ],
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_dns_cloudflare_rejects_loose_mode(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    fake_env: _FakeDockerEnv,
    tmp_path: Path,
) -> None:
    creds = _make_creds(tmp_path, mode=0o644)  # group/world-readable
    result = runner.invoke(
        app,
        [
            "tls",
            "request",
            "--yes",
            "-d",
            "example.com",
            "--email",
            "ops@example.com",
            "--method",
            "dns-cloudflare",
            "--credentials",
            str(creds),
        ],
    )
    assert result.exit_code == 1
    assert "0600" in result.output or "chmod 600" in result.output


def test_dns_cloudflare_happy_path_picks_dns_image(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    fake_env: _FakeDockerEnv,
    tmp_path: Path,
) -> None:
    creds = _make_creds(tmp_path)
    result = runner.invoke(
        app,
        [
            "tls",
            "request",
            "--yes",
            "-d",
            "example.com",
            "-d",
            "*.example.com",
            "--email",
            "ops@example.com",
            "--method",
            "dns-cloudflare",
            "--credentials",
            str(creds),
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(fake_env.calls) == 1
    call = fake_env.calls[0]
    # Picks the dns-cloudflare image, not the webroot image.
    assert call["image"] == "certbot/dns-cloudflare:v3.0.1"
    cmd = call["command"]
    assert isinstance(cmd, list)
    assert "--dns-cloudflare" in cmd
    # Credentials parent dir mounted.
    volumes = call["volumes"]
    assert isinstance(volumes, dict)
    assert str(creds.parent) in volumes
    assert volumes[str(creds.parent)]["bind"] == "/credentials"


def test_dns_cloudflare_json_includes_method(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    fake_env: _FakeDockerEnv,
    tmp_path: Path,
) -> None:
    creds = _make_creds(tmp_path)
    result = runner.invoke(
        app,
        [
            "tls",
            "request",
            "--yes",
            "--json",
            "-d",
            "example.com",
            "--email",
            "ops@example.com",
            "--method",
            "dns-cloudflare",
            "--credentials",
            str(creds),
        ],
    )
    assert result.exit_code == 0
    doc = json.loads(result.output)
    assert doc["data"]["method"] == "dns-cloudflare"
    assert doc["data"]["domains"] == ["example.com"]


def test_webroot_still_picks_webroot_image(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    fake_env: _FakeDockerEnv,
    tmp_path: Path,
) -> None:
    """The default webroot path still uses the original certbot/certbot image."""
    webroot = tmp_path / "www"
    webroot.mkdir()
    result = runner.invoke(
        app,
        [
            "tls",
            "request",
            "--yes",
            "-d",
            "example.com",
            "--email",
            "ops@example.com",
            "--webroot",
            str(webroot),
        ],
    )
    assert result.exit_code == 0, result.output
    assert fake_env.calls[0]["image"] == "certbot/certbot:v3.0.1"


def test_webroot_still_requires_webroot_arg(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, fake_env: _FakeDockerEnv
) -> None:
    """Missing --webroot for the webroot method still errors."""
    result = runner.invoke(
        app,
        [
            "tls",
            "request",
            "--yes",
            "-d",
            "example.com",
            "--email",
            "ops@example.com",
        ],
    )
    assert result.exit_code == 1
    assert "--webroot is required" in result.output.lower()


# ─── config plumbing ──────────────────────────────────────────────────


def test_tls_config_has_cloudflare_image() -> None:
    from shimkit.config import get_config

    cfg = get_config().tools.tls
    assert cfg.certbot_dns_cloudflare_image == "certbot/dns-cloudflare:v3.0.1"
    assert cfg.cloudflare_propagation_seconds == 60


def test_tls_config_propagation_can_be_zero() -> None:
    """Lower bound — propagation_seconds=0 is allowed for tests / very
    fast accounts (Field has ge=0)."""
    from shimkit.config.schema import TlsConfig

    cfg = TlsConfig(cloudflare_propagation_seconds=0)
    assert cfg.cloudflare_propagation_seconds == 0


def test_tls_config_propagation_rejects_negative() -> None:
    from pydantic import ValidationError

    from shimkit.config.schema import TlsConfig

    with pytest.raises(ValidationError):
        TlsConfig(cloudflare_propagation_seconds=-1)
