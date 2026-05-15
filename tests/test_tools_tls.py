"""Tests for ``shimkit tls``."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult, ExecOutcome
from shimkit.core.platform import Platform
from shimkit.tools.tls import certbot
from shimkit.tools.tls.manager import TlsManager, _is_valid_domain

# ─── pure argv builders ─────────────────────────────────────────────────


def test_request_argv_minimal() -> None:
    argv = certbot.request_argv(
        domains=["example.com"], email="ops@example.com", method="webroot"
    )
    assert argv[0] == "certonly"
    assert "--non-interactive" in argv
    assert "--agree-tos" in argv
    assert "--email" in argv and "ops@example.com" in argv
    assert "--webroot" in argv
    assert argv[-2:] == ["-d", "example.com"]


def test_request_argv_multiple_domains() -> None:
    argv = certbot.request_argv(
        domains=["example.com", "www.example.com", "api.example.com"],
        email="ops@example.com",
        method="webroot",
    )
    # Each -d/<domain> pair appears in order.
    d_pairs = [(argv[i], argv[i + 1]) for i, t in enumerate(argv) if t == "-d"]
    assert d_pairs == [
        ("-d", "example.com"),
        ("-d", "www.example.com"),
        ("-d", "api.example.com"),
    ]


def test_request_argv_staging_and_dry_run() -> None:
    argv = certbot.request_argv(
        domains=["a.com"], email="o@a.com", method="webroot", staging=True, dry_run=True
    )
    assert "--staging" in argv
    assert "--dry-run" in argv


def test_request_argv_rejects_empty_domains() -> None:
    with pytest.raises(ValueError):
        certbot.request_argv(domains=[], email="o@a.com", method="webroot")


def test_request_argv_rejects_unsupported_method() -> None:
    with pytest.raises(ValueError):
        certbot.request_argv(
            domains=["a.com"],
            email="o@a.com",
            method="dns",  # type: ignore[arg-type]
        )


def test_renew_argv_default() -> None:
    argv = certbot.renew_argv()
    assert argv == ["renew", "--non-interactive"]


def test_renew_argv_with_cert_name() -> None:
    argv = certbot.renew_argv(cert_name="example.com")
    assert "--cert-name" in argv
    assert "example.com" in argv


def test_renew_argv_force_and_dry_run() -> None:
    argv = certbot.renew_argv(force=True, dry_run=True)
    assert "--force-renewal" in argv
    assert "--dry-run" in argv


def test_revoke_argv() -> None:
    argv = certbot.revoke_argv(cert_name="example.com")
    assert argv[0] == "revoke"
    assert "--cert-name" in argv and "example.com" in argv


def test_revoke_argv_rejects_empty_name() -> None:
    with pytest.raises(ValueError):
        certbot.revoke_argv(cert_name="")


def test_container_volumes_includes_etc_and_var_lib(tmp_path: Path) -> None:
    vols = certbot.container_volumes(data_dir=tmp_path)
    bind_points = {v["bind"] for v in vols.values()}
    assert "/etc/letsencrypt" in bind_points
    assert "/var/lib/letsencrypt" in bind_points
    assert "/webroot" not in bind_points


def test_container_volumes_with_webroot(tmp_path: Path) -> None:
    webroot = tmp_path / "www"
    webroot.mkdir()
    vols = certbot.container_volumes(data_dir=tmp_path, webroot=webroot)
    assert str(webroot) in vols
    assert vols[str(webroot)]["bind"] == "/webroot"
    assert vols[str(webroot)]["mode"] == "ro"


def test_cert_paths_under_live_dir(tmp_path: Path) -> None:
    fullchain, privkey = certbot.cert_paths(data_dir=tmp_path, domain="example.com")
    assert fullchain.name == "fullchain.pem"
    assert privkey.name == "privkey.pem"
    assert fullchain.parent.name == "example.com"
    assert fullchain.parent.parent.name == "live"


# ─── domain validation ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "example.com",
        "sub.example.com",
        "api-v2.example.com",
        "a.io",
        "deep.sub.example.co.uk",
    ],
)
def test_valid_domains(name: str) -> None:
    assert _is_valid_domain(name)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "example",
        ".example.com",
        "example.com.",
        "example..com",
        "-example.com",
        "example-.com",
        "a" * 64 + ".com",  # label too long
    ],
)
def test_invalid_domains(name: str) -> None:
    assert not _is_valid_domain(name)


# ─── helpers ────────────────────────────────────────────────────────────


class _FakeDockerEnv:
    """Mock DockerEnv that records `run_oneshot` calls without touching docker."""

    def __init__(self, outcome: ExecOutcome | None = None) -> None:
        self.outcome = outcome or ExecOutcome(exit_code=0, stdout="ok", stderr="")
        self.calls: list[dict[str, object]] = []

    @classmethod
    def create(cls) -> _FakeDockerEnv:
        return cls()

    def boot(self) -> _FakeDockerEnv:
        return self

    def run_oneshot(self, image: str, **kwargs: object) -> ExecOutcome:
        self.calls.append({"image": image, **kwargs})
        return self.outcome


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch) -> _FakeDockerEnv:
    """Replace the DockerEnv used inside the tls manager."""
    inst = _FakeDockerEnv()

    class _Factory:
        @classmethod
        def create(cls) -> _FakeDockerEnv:
            return inst

    monkeypatch.setattr("shimkit.tools.tls.manager.DockerEnv", _Factory)
    return inst


def _bypass_version_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shimkit.tools.tls.manager._vc.preflight", lambda *a, **kw: None)


def _force_unix(monkeypatch: pytest.MonkeyPatch, system: str = "Linux") -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system=system, machine="x86_64")),
    )


def _redirect_tls_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point tools.tls.data_dir at tmp_path so tests don't write to $HOME."""
    monkeypatch.setenv("HOME", str(tmp_path))
    from shimkit.config import reset_cache

    reset_cache()


@pytest.fixture(autouse=True)
def _autouse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_unix(monkeypatch)
    _bypass_version_preflight(monkeypatch)
    _redirect_tls_dir(monkeypatch, tmp_path)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── boot ───────────────────────────────────────────────────────────────


def test_boot_creates_data_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_env: _FakeDockerEnv
) -> None:
    TlsManager.create().boot()
    data_dir = tmp_path / ".shimkit" / "data" / "tls"
    assert (data_dir / "etc-letsencrypt").is_dir()
    assert (data_dir / "var-lib-letsencrypt").is_dir()


# ─── request ────────────────────────────────────────────────────────────


def test_request_rejects_missing_email(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_env: _FakeDockerEnv
) -> None:
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
            "--webroot",
            str(webroot),
        ],
    )
    assert result.exit_code == 1
    assert "email" in result.stdout.lower()


def test_request_rejects_missing_webroot(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_env: _FakeDockerEnv
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
            "--webroot",
            str(tmp_path / "nope"),
        ],
    )
    assert result.exit_code == 1
    assert "webroot" in result.stdout.lower()


def test_request_rejects_invalid_domain(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_env: _FakeDockerEnv
) -> None:
    webroot = tmp_path / "www"
    webroot.mkdir()
    result = runner.invoke(
        app,
        [
            "tls",
            "request",
            "--yes",
            "-d",
            "not_a_domain",
            "--email",
            "ops@example.com",
            "--webroot",
            str(webroot),
        ],
    )
    assert result.exit_code == 1
    assert "invalid domain" in result.stdout.lower()


def test_request_passes_argv_and_volumes_to_oneshot(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_env: _FakeDockerEnv
) -> None:
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
            "-d",
            "www.example.com",
            "--email",
            "ops@example.com",
            "--webroot",
            str(webroot),
            "--staging",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert len(fake_env.calls) == 1
    call = fake_env.calls[0]
    assert call["image"] == "certbot/certbot:v3.0.1"
    cmd = call["command"]
    assert isinstance(cmd, list)
    assert cmd[0] == "certonly"
    assert "--staging" in cmd
    assert "-d" in cmd and "example.com" in cmd and "www.example.com" in cmd
    volumes = call["volumes"]
    assert isinstance(volumes, dict)
    assert str(webroot) in volumes


def test_request_propagates_failure_exit(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inst = _FakeDockerEnv(
        outcome=ExecOutcome(exit_code=1, stdout="", stderr="some certbot error")
    )

    class _Factory:
        @classmethod
        def create(cls) -> _FakeDockerEnv:
            return inst

    monkeypatch.setattr("shimkit.tools.tls.manager.DockerEnv", _Factory)
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
    assert result.exit_code == 1
    assert "some certbot error" in result.stdout


def test_request_json_includes_domains_and_status(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_env: _FakeDockerEnv
) -> None:
    webroot = tmp_path / "www"
    webroot.mkdir()
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
            "--webroot",
            str(webroot),
        ],
    )
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["status"] == "ok"
    assert doc["data"]["domains"] == ["example.com"]


# ─── renew ──────────────────────────────────────────────────────────────


def test_renew_default_runs_certbot_renew(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, fake_env: _FakeDockerEnv
) -> None:
    result = runner.invoke(app, ["tls", "renew", "--yes"])
    assert result.exit_code == 0, result.stdout
    assert fake_env.calls[0]["command"] == ["renew", "--non-interactive"]


def test_renew_with_domain_passes_cert_name(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, fake_env: _FakeDockerEnv
) -> None:
    runner.invoke(app, ["tls", "renew", "--yes", "-d", "example.com"])
    cmd = fake_env.calls[0]["command"]
    assert isinstance(cmd, list)
    assert "--cert-name" in cmd
    assert "example.com" in cmd


def test_renew_force_renewal_flag(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, fake_env: _FakeDockerEnv
) -> None:
    runner.invoke(app, ["tls", "renew", "--yes", "--force-renewal"])
    assert "--force-renewal" in fake_env.calls[0]["command"]


# ─── revoke ─────────────────────────────────────────────────────────────


def test_revoke_requires_severe_token(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, fake_env: _FakeDockerEnv
) -> None:
    result = runner.invoke(app, ["tls", "revoke", "-d", "example.com"])
    assert result.exit_code == 1
    assert "REVOKE-TLS" in result.stdout


def test_revoke_with_token_requires_existing_cert(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_env: _FakeDockerEnv
) -> None:
    # Cert dir absent -> error before invoking certbot.
    result = runner.invoke(
        app, ["tls", "revoke", "-d", "example.com", "--confirm", "REVOKE-TLS"]
    )
    assert result.exit_code == 1
    assert "no cert" in result.stdout.lower()


def test_revoke_with_token_and_existing_cert_runs(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_env: _FakeDockerEnv
) -> None:
    # Pre-populate the live dir so the manager sees the cert.
    live = (
        tmp_path
        / ".shimkit"
        / "data"
        / "tls"
        / "etc-letsencrypt"
        / "live"
        / "example.com"
    )
    live.mkdir(parents=True)
    (live / "fullchain.pem").write_text("not really a cert")
    result = runner.invoke(
        app, ["tls", "revoke", "-d", "example.com", "--confirm", "REVOKE-TLS"]
    )
    assert result.exit_code == 0, result.stdout
    assert fake_env.calls[0]["command"][0] == "revoke"


# ─── list / status ──────────────────────────────────────────────────────


def _seed_cert(
    tmp_path: Path,
    *,
    domain: str = "example.com",
    body: str = "fake-pem",
) -> Path:
    live = (
        tmp_path
        / ".shimkit"
        / "data"
        / "tls"
        / "etc-letsencrypt"
        / "live"
        / domain
    )
    live.mkdir(parents=True)
    fullchain = live / "fullchain.pem"
    fullchain.write_text(body)
    (live / "privkey.pem").write_text("fake-key")
    return fullchain


def test_list_empty_when_no_certs(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, fake_env: _FakeDockerEnv
) -> None:
    result = runner.invoke(app, ["tls", "list", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["certs"] == []


def test_list_reports_certs_with_expiry(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_env: _FakeDockerEnv
) -> None:
    _seed_cert(tmp_path, domain="example.com")
    # Stub openssl to return a known expiry.
    future = datetime.now(tz=timezone.utc) + timedelta(days=60)
    notafter = future.strftime("notAfter=%b %d %H:%M:%S %Y GMT")

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        if list(cmd)[:2] == ["openssl", "x509"]:
            return CommandResult(0, notafter, "")
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.tls.manager.CommandRunner.run", staticmethod(fake_run)
    )
    result = runner.invoke(app, ["tls", "list", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    cert = doc["data"]["certs"][0]
    assert cert["domain"] == "example.com"
    assert cert["expires_at"] is not None
    assert cert["days_remaining"] is not None
    assert not cert["expiring_soon"]


def test_list_flags_expiring_soon(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_env: _FakeDockerEnv
) -> None:
    _seed_cert(tmp_path, domain="example.com")
    soon = datetime.now(tz=timezone.utc) + timedelta(days=10)
    notafter = soon.strftime("notAfter=%b %d %H:%M:%S %Y GMT")

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        if list(cmd)[:2] == ["openssl", "x509"]:
            return CommandResult(0, notafter, "")
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.tls.manager.CommandRunner.run", staticmethod(fake_run)
    )
    result = runner.invoke(app, ["tls", "list", "--json"])
    cert = json.loads(result.stdout)["data"]["certs"][0]
    assert cert["expiring_soon"] is True


def test_status_missing_cert(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, fake_env: _FakeDockerEnv
) -> None:
    result = runner.invoke(app, ["tls", "status", "example.com"])
    assert result.exit_code == 1
    assert "no cert" in result.stdout.lower()


def test_status_existing_cert_json(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_env: _FakeDockerEnv
) -> None:
    _seed_cert(tmp_path, domain="example.com")
    future = datetime.now(tz=timezone.utc) + timedelta(days=42)
    notafter = future.strftime("notAfter=%b %d %H:%M:%S %Y GMT")

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        return CommandResult(0, notafter, "")

    monkeypatch.setattr(
        "shimkit.tools.tls.manager.CommandRunner.run", staticmethod(fake_run)
    )
    result = runner.invoke(app, ["tls", "status", "example.com", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["domain"] == "example.com"


# ─── cron-install ───────────────────────────────────────────────────────


def test_cron_install_delegates_to_cron_manager(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_env: _FakeDockerEnv
) -> None:
    seen: dict[str, object] = {}

    class FakeCronManager:
        @classmethod
        def create(cls):
            return cls()

        def boot(self):
            return self

        def add(self, **kw):  # type: ignore[no-untyped-def]
            seen.update(kw)
            return 0

    monkeypatch.setattr("shimkit.tools.cron.manager.CronManager", FakeCronManager)
    result = runner.invoke(app, ["tls", "cron-install", "--yes", "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert seen["name"] == "tls-renew"
    assert seen["schedule"] == "17 3 * * *"
    assert "shimkit tls renew" in str(seen["command"])
    assert seen["dry_run"] is True


def test_cron_install_custom_schedule(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, fake_env: _FakeDockerEnv
) -> None:
    seen: dict[str, object] = {}

    class FakeCronManager:
        @classmethod
        def create(cls):
            return cls()

        def boot(self):
            return self

        def add(self, **kw):  # type: ignore[no-untyped-def]
            seen.update(kw)
            return 0

    monkeypatch.setattr("shimkit.tools.cron.manager.CronManager", FakeCronManager)
    runner.invoke(
        app, ["tls", "cron-install", "--yes", "--dry-run", "--schedule", "30 4 * * *"]
    )
    assert seen["schedule"] == "30 4 * * *"


# ─── command surface ────────────────────────────────────────────────────


def test_tls_help_lists_all_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["tls", "--help"])
    assert result.exit_code == 0
    for sub in ("request", "list", "status", "renew", "revoke", "cron-install"):
        assert sub in result.output


def test_openssl_in_versions_audit() -> None:
    from shimkit.config import get_config
    from shimkit.core import version as _vc

    assert "openssl" in _vc._DETECTORS
    assert get_config().tools.versions.openssl.min == "1.1"
