"""Tests for the v0.17.0 DNS-01 (Route53) addition to shimkit tls.

The Cloudflare flow lives in test_tools_tls_dns_cloudflare.py; this
file covers the new --method dns-route53 path:

- request_argv shape (--dns-route53 + propagation-seconds; no
  --dns-route53-credentials flag because boto3 reads
  ~/.aws/credentials by default)
- container_volumes mounts the credentials file at
  /root/.aws/credentials (not /credentials/*) when
  credentials_mount="route53"
- manager validates --credentials presence + mode 0600 (same
  refusals as Cloudflare)
- manager picks the certbot/dns-route53 image
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def test_request_argv_dns_route53_shape() -> None:
    argv = certbot.request_argv(
        domains=["example.com", "*.example.com"],
        email="ops@example.com",
        method="dns-route53",
    )
    assert "--dns-route53" in argv
    assert "--dns-route53-propagation-seconds" in argv
    idx = argv.index("--dns-route53-propagation-seconds")
    assert argv[idx + 1] == "60"
    # No --dns-route53-credentials flag — boto3 picks up
    # ~/.aws/credentials inside the container.
    assert "--dns-route53-credentials" not in argv
    # No --dns-cloudflare bleed.
    assert "--dns-cloudflare" not in argv
    # No --webroot bleed.
    assert "--webroot" not in argv
    # Wildcard domain passes through.
    assert "*.example.com" in argv


def test_request_argv_dns_route53_staging_and_dry_run() -> None:
    argv = certbot.request_argv(
        domains=["example.com"],
        email="ops@example.com",
        method="dns-route53",
        staging=True,
        dry_run=True,
    )
    assert "--staging" in argv
    assert "--dry-run" in argv


def test_request_argv_dns_route53_propagation_override() -> None:
    argv = certbot.request_argv(
        domains=["example.com"],
        email="ops@example.com",
        method="dns-route53",
        propagation_seconds=30,
    )
    idx = argv.index("--dns-route53-propagation-seconds")
    assert argv[idx + 1] == "30"


# ─── container_volumes — route53 mount target ─────────────────────────


def test_container_volumes_route53_mounts_file_at_aws_credentials(
    tmp_path: Path,
) -> None:
    creds = tmp_path / "aws-credentials"
    creds.write_text("[default]\naws_access_key_id = X\naws_secret_access_key = Y\n")
    vols = certbot.container_volumes(
        data_dir=tmp_path, credentials=creds, credentials_mount="route53"
    )
    # File itself bound at /root/.aws/credentials — different from
    # Cloudflare's parent-dir-at-/credentials shape.
    assert str(creds) in vols
    assert vols[str(creds)]["bind"] == "/root/.aws/credentials"
    assert vols[str(creds)]["mode"] == "ro"
    # The /credentials mount should NOT be present in route53 mode.
    bind_points = {v["bind"] for v in vols.values()}
    assert "/credentials" not in bind_points


def test_container_volumes_cloudflare_still_mounts_parent_dir(
    tmp_path: Path,
) -> None:
    """The default credentials_mount path is cloudflare (regression
    guard — adding route53 didn't change Cloudflare's mount shape)."""
    creds_dir = tmp_path / "secrets"
    creds_dir.mkdir()
    creds = creds_dir / "cloudflare.ini"
    creds.write_text("dns_cloudflare_api_token = token123\n")
    vols = certbot.container_volumes(data_dir=tmp_path, credentials=creds)
    # Parent dir mounted at /credentials (not the file at
    # /root/.aws/credentials).
    assert str(creds_dir) in vols
    assert vols[str(creds_dir)]["bind"] == "/credentials"


# ─── manager: route53 happy path + refusals ────────────────────────────


class _FakeDockerEnv:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

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


def _make_aws_creds(tmp_path: Path, *, mode: int = 0o600) -> Path:
    """Create a valid-shaped AWS credentials file."""
    creds = tmp_path / "aws-credentials"
    creds.write_text(
        "[default]\n"
        "aws_access_key_id = AKIAIOSFODNN7EXAMPLE\n"
        "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n"
    )
    creds.chmod(mode)
    return creds


def test_dns_route53_requires_credentials(
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
            "dns-route53",
        ],
    )
    assert result.exit_code == 1
    assert "credentials" in result.output.lower()


def test_dns_route53_rejects_missing_creds_file(
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
            "dns-route53",
            "--credentials",
            str(tmp_path / "absent"),
        ],
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_dns_route53_rejects_loose_mode(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    fake_env: _FakeDockerEnv,
    tmp_path: Path,
) -> None:
    creds = _make_aws_creds(tmp_path, mode=0o644)
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
            "dns-route53",
            "--credentials",
            str(creds),
        ],
    )
    assert result.exit_code == 1
    assert "0600" in result.output or "chmod 600" in result.output


def test_dns_route53_happy_path_picks_route53_image(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    fake_env: _FakeDockerEnv,
    tmp_path: Path,
) -> None:
    creds = _make_aws_creds(tmp_path)
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
            "dns-route53",
            "--credentials",
            str(creds),
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(fake_env.calls) == 1
    call = fake_env.calls[0]
    # Picks the route53 image, not Cloudflare or generic.
    assert call["image"] == "certbot/dns-route53:v3.0.1"
    cmd = call["command"]
    assert isinstance(cmd, list)
    assert "--dns-route53" in cmd
    # Credentials file mounted at /root/.aws/credentials.
    volumes = call["volumes"]
    assert isinstance(volumes, dict)
    assert str(creds) in volumes
    assert volumes[str(creds)]["bind"] == "/root/.aws/credentials"
    assert volumes[str(creds)]["mode"] == "ro"


def test_dns_route53_json_includes_method(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    fake_env: _FakeDockerEnv,
    tmp_path: Path,
) -> None:
    creds = _make_aws_creds(tmp_path)
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
            "dns-route53",
            "--credentials",
            str(creds),
        ],
    )
    assert result.exit_code == 0
    doc = json.loads(result.output)
    assert doc["data"]["method"] == "dns-route53"


def test_dns_route53_uses_route53_propagation_seconds(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    fake_env: _FakeDockerEnv,
    tmp_path: Path,
) -> None:
    """The manager threads tools.tls.route53_propagation_seconds
    (not cloudflare_propagation_seconds) into the argv."""
    creds = _make_aws_creds(tmp_path)
    # Override the config value via env wouldn't work cleanly here
    # — just verify the default reaches the argv.
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
            "dns-route53",
            "--credentials",
            str(creds),
        ],
    )
    assert result.exit_code == 0
    cmd = fake_env.calls[0]["command"]
    idx = cmd.index("--dns-route53-propagation-seconds")
    assert cmd[idx + 1] == "60"


# ─── config plumbing ──────────────────────────────────────────────────


def test_tls_config_has_route53_image() -> None:
    from shimkit.config import get_config

    cfg = get_config().tools.tls
    assert cfg.certbot_dns_route53_image == "certbot/dns-route53:v3.0.1"
    assert cfg.route53_propagation_seconds == 60


def test_tls_config_route53_propagation_range() -> None:
    from pydantic import ValidationError

    from shimkit.config.schema import TlsConfig

    # Within range
    TlsConfig(route53_propagation_seconds=0)
    TlsConfig(route53_propagation_seconds=600)
    # Out of range
    with pytest.raises(ValidationError):
        TlsConfig(route53_propagation_seconds=-1)
    with pytest.raises(ValidationError):
        TlsConfig(route53_propagation_seconds=601)


# ─── webroot path unaffected ──────────────────────────────────────────


def test_webroot_unaffected_by_route53_addition(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    fake_env: _FakeDockerEnv,
    tmp_path: Path,
) -> None:
    """Regression: adding route53 didn't break the original webroot flow."""
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
    assert result.exit_code == 0
    assert fake_env.calls[0]["image"] == "certbot/certbot:v3.0.1"
