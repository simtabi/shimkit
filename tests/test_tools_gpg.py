"""Tests for ``shimkit gpg``.

``gpg`` and ``git`` are mocked at ``CommandRunner.run``. The pure
parsers (``parse_list_keys`` + ``parse_git_signing_config``) are
exercised against fixture strings.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult
from shimkit.core.platform import Platform
from shimkit.tools.gpg.manager import GpgManager


def _force_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    # `gpg` always-present in the test path.
    monkeypatch.setattr("shimkit.tools.gpg.manager.shutil.which", lambda _: "/usr/bin/gpg")


# ─── pure parser: list_keys ─────────────────────────────────────────────


def test_parse_list_keys_ed25519_single_key() -> None:
    from shimkit.tools.gpg.parser import parse_list_keys

    # Synthetic --with-colons output. Field 5 is created timestamp,
    # field 6 is expiry. Both as unix epoch.
    text = (
        "pub:u:256:22:ABCD1234EF567890:1700000000:1800000000::u:::::::::ed25519:\n"
        "fpr:::::::::ABCDEF1234567890ABCDEF1234567890ABCDEF12:\n"
        "uid:u::::::::Test User <test@example.com>::\n"
    )
    keys = parse_list_keys(text)
    assert len(keys) == 1
    k = keys[0]
    assert k.key_id == "ABCD1234EF567890"
    assert k.fingerprint == "ABCDEF1234567890ABCDEF1234567890ABCDEF12"
    assert k.key_type == "ed25519"
    assert k.bits == 256
    assert k.uids == ("Test User <test@example.com>",)
    # Created 1700000000 = 2023-11-14 in UTC.
    assert k.created.startswith("2023-")


def test_parse_list_keys_rsa_multiple_keys() -> None:
    from shimkit.tools.gpg.parser import parse_list_keys

    text = (
        "pub:u:3072:1:AAAA1111BBBB2222:1700000000:1731536000::u:::::::::rsa:\n"
        "fpr:::::::::FPR1:\n"
        "uid:u::::::::User 1 <u1@example.com>::\n"
        "pub:u:4096:1:CCCC3333DDDD4444:1700000000:0::u:::::::::rsa:\n"
        "fpr:::::::::FPR2:\n"
        "uid:u::::::::User 2 <u2@example.com>::\n"
    )
    keys = parse_list_keys(text)
    assert len(keys) == 2
    assert keys[0].key_type == "rsa" and keys[0].bits == 3072
    assert keys[1].expires is None  # 0 → never


def test_parse_list_keys_empty() -> None:
    from shimkit.tools.gpg.parser import parse_list_keys

    assert parse_list_keys("") == []


def test_gpgkey_is_expired() -> None:
    from shimkit.tools.gpg.models import GpgKey

    expired = GpgKey(
        key_id="X",
        fingerprint="F",
        key_type="ed25519",
        bits=256,
        created="2020-01-01",
        expires="2020-12-31",
        uids=(),
    )
    never = GpgKey(
        key_id="Y",
        fingerprint="F",
        key_type="ed25519",
        bits=256,
        created="2020-01-01",
        expires=None,
        uids=(),
    )
    assert expired.is_expired is True
    assert never.is_expired is False


def test_parse_git_signing_config() -> None:
    from shimkit.tools.gpg.parser import parse_git_signing_config

    stdout = (
        "user.signingkey ABCD1234\n"
        "commit.gpgsign true\n"
        "user.name Alice\n"  # unrelated; ignored
    )
    cfg = parse_git_signing_config(stdout)
    assert cfg["user.signingkey"] == "ABCD1234"
    assert cfg["commit.gpgsign"] == "true"
    assert cfg["gpg.format"] is None


# ─── manager: platform / gpg-missing ────────────────────────────────────


def test_boot_exits_69_on_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Windows", machine="x86_64")),
    )
    with pytest.raises(SystemExit) as exc:
        GpgManager.create().boot()
    assert exc.value.code == 69


def test_boot_exits_69_when_gpg_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )
    monkeypatch.setattr("shimkit.tools.gpg.manager.shutil.which", lambda _: None)
    with pytest.raises(SystemExit) as exc:
        GpgManager.create().boot()
    assert exc.value.code == 69


# ─── keys list ──────────────────────────────────────────────────────────


def test_gpg_keys_list_empty(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, "", "")),
    )
    result = runner.invoke(app, ["gpg", "keys", "list", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["keys"] == []


def test_gpg_keys_list_one_key_via_json(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    stdout = (
        "pub:u:256:22:ABCD1234EF567890:1700000000:1800000000::u:::::::::ed25519:\n"
        "fpr:::::::::ABCDEF1234567890ABCDEF1234567890ABCDEF12:\n"
        "uid:u::::::::Test User <test@example.com>::\n"
    )
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, stdout, "")),
    )
    result = runner.invoke(app, ["gpg", "keys", "list", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert len(doc["data"]["keys"]) == 1
    k = doc["data"]["keys"][0]
    assert k["key_id"] == "ABCD1234EF567890"
    assert k["type"] == "ed25519"


# ─── keys generate ──────────────────────────────────────────────────────


def test_gpg_keys_generate_invokes_gpg(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    captured: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        captured.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run", staticmethod(fake_run)
    )
    result = runner.invoke(
        app,
        [
            "gpg",
            "keys",
            "generate",
            "Test User",
            "test@example.com",
            "--type",
            "ed25519",
            "--yes",
        ],
    )
    assert result.exit_code == 0
    assert captured and captured[0][:2] == ["gpg", "--quick-gen-key"]
    # UID composed correctly.
    assert "Test User <test@example.com>" in captured[0]
    assert "ed25519" in captured[0]


def test_gpg_keys_generate_refuses_unknown_type(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, "", "")),
    )
    result = runner.invoke(
        app,
        [
            "gpg",
            "keys",
            "generate",
            "T",
            "t@example.com",
            "--type",
            "rsa1024",
            "--yes",
        ],
    )
    assert result.exit_code == 1
    assert "Unknown key type" in result.stdout


def test_gpg_keys_generate_dry_run_does_not_invoke_gpg(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    captured: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        captured.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run", staticmethod(fake_run)
    )
    result = runner.invoke(
        app,
        [
            "gpg",
            "keys",
            "generate",
            "T",
            "t@example.com",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    # In dry-run no quick-gen-key is invoked.
    assert all(c[:2] != ["gpg", "--quick-gen-key"] for c in captured)


# ─── keys export ────────────────────────────────────────────────────────


def test_gpg_keys_export_to_stdout(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    armoured = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nfake\n-----END PGP PUBLIC KEY BLOCK-----\n"
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, armoured, "")),
    )
    result = runner.invoke(app, ["gpg", "keys", "export", "ABCD1234"])
    assert result.exit_code == 0
    assert "BEGIN PGP PUBLIC KEY BLOCK" in result.stdout


def test_gpg_keys_export_to_file(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _force_linux(monkeypatch)
    armoured = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nfake\n-----END PGP PUBLIC KEY BLOCK-----\n"
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, armoured, "")),
    )
    out = tmp_path / "public.asc"
    result = runner.invoke(
        app, ["gpg", "keys", "export", "ABCD1234", "--dest", str(out)]
    )
    assert result.exit_code == 0
    assert out.read_text().startswith("-----BEGIN PGP PUBLIC KEY BLOCK-----")


# ─── agent ──────────────────────────────────────────────────────────────


def test_gpg_agent_status_up(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, "", "")),
    )
    result = runner.invoke(app, ["gpg", "agent", "status", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["agent_running"] is True


def test_gpg_agent_status_down(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(2, "", "gpg-connect-agent: no agent")),
    )
    result = runner.invoke(app, ["gpg", "agent", "status", "--json"])
    assert result.exit_code == 1
    doc = json.loads(result.stdout)
    assert doc["data"]["agent_running"] is False


# ─── git-signing ────────────────────────────────────────────────────────


def test_gpg_git_signing_show(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.shutil.which",
        lambda b: "/usr/bin/" + b,
    )
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(
            lambda _cmd, **_: CommandResult(
                0, "user.signingkey ABCD1234\ncommit.gpgsign true\n", ""
            )
        ),
    )
    result = runner.invoke(app, ["gpg", "git-signing", "show", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["config"]["user.signingkey"] == "ABCD1234"
    assert doc["data"]["config"]["commit.gpgsign"] == "true"


def test_gpg_git_signing_configure_writes_two_git_configs(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.shutil.which",
        lambda b: "/usr/bin/" + b,
    )
    captured: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        captured.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run", staticmethod(fake_run)
    )
    result = runner.invoke(
        app,
        ["gpg", "git-signing", "configure", "ABCD1234", "--yes"],
    )
    assert result.exit_code == 0
    # Two `git config --global` writes: signingkey + gpgsign.
    git_cmds = [c for c in captured if c[0] == "git"]
    assert len(git_cmds) == 2
    assert ["git", "config", "--global", "user.signingkey", "ABCD1234"] in git_cmds
    assert ["git", "config", "--global", "commit.gpgsign", "true"] in git_cmds


def test_gpg_git_signing_configure_rejects_unknown_scope(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.shutil.which",
        lambda b: "/usr/bin/" + b,
    )
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, "", "")),
    )
    result = runner.invoke(
        app,
        [
            "gpg",
            "git-signing",
            "configure",
            "ABCD1234",
            "--scope",
            "system",
            "--yes",
        ],
    )
    assert result.exit_code == 1
    assert "Unknown scope" in result.stdout


# ─── moderate prompt ────────────────────────────────────────────────────


def test_gpg_keys_generate_refuses_under_no_input(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.gpg.manager.CommandRunner.run",
        staticmethod(lambda _cmd, **_: CommandResult(0, "", "")),
    )
    result = runner.invoke(
        app,
        [
            "gpg",
            "--no-input",
            "keys",
            "generate",
            "T",
            "t@example.com",
        ],
    )
    assert result.exit_code == 1
    assert "Cancelled" in result.stdout or "Pass --yes" in result.stdout
