"""Tests for ``shimkit ssh``.

Filesystem ops run against ``tmp_path`` via the ``--ssh-dir``
override. ``ssh-keygen`` / ``ssh-add`` / ``ssh`` are monkeypatched at
``CommandRunner.run`` so no real binaries fire.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app
from shimkit.core import CommandResult


def _force_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )


# ─── pure scanner ───────────────────────────────────────────────────────


def test_list_keys_finds_ed25519_pair(tmp_path: Path) -> None:
    from shimkit.tools.ssh.scanner import list_keys

    priv = tmp_path / "id_ed25519"
    priv.write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "AAAA-something-fake\n"
        "-----END OPENSSH PRIVATE KEY-----\n"
    )
    pub = tmp_path / "id_ed25519.pub"
    pub.write_text("ssh-ed25519 AAAA-pub-fake user@host\n")
    keys = list_keys(tmp_path)
    assert len(keys) == 1
    k = keys[0]
    assert k.private == priv and k.public == pub
    assert k.key_type == "ed25519"
    assert k.comment == "user@host"


def test_list_keys_ignores_random_files(tmp_path: Path) -> None:
    from shimkit.tools.ssh.scanner import list_keys

    (tmp_path / "config").write_text("Host *\n")
    (tmp_path / "known_hosts").write_text("")
    (tmp_path / "id_ed25519.pub").write_text("ssh-ed25519 AAAA u@h\n")
    assert list_keys(tmp_path) == []


def test_parse_agent_keys_l_format() -> None:
    from shimkit.tools.ssh.scanner import parse_agent_keys

    text = (
        "256 SHA256:abcdef123 user@host (ED25519)\n"
        "3072 SHA256:fedcba987 (RSA)\n"
    )
    rows = parse_agent_keys(text)
    assert rows[0]["type"] == "ED25519"
    assert rows[0]["fingerprint"] == "SHA256:abcdef123"
    assert rows[0]["comment"] == "user@host"
    assert rows[1]["type"] == "RSA"


def test_parse_agent_keys_empty_agent() -> None:
    from shimkit.tools.ssh.scanner import parse_agent_keys

    assert parse_agent_keys("The agent has no identities.\n") == []


def test_find_known_host_duplicates() -> None:
    from shimkit.tools.ssh.scanner import find_known_host_duplicates

    text = (
        "host1 ssh-ed25519 AAA1\n"
        "# comment\n"
        "host2 ssh-ed25519 AAA2\n"
        "host1 ssh-ed25519 AAA1\n"
    )
    dupes = find_known_host_duplicates(text)
    assert len(dupes) == 1
    host, lines = dupes[0]
    assert host == "host1"
    assert lines == [0, 3]


def test_prune_known_hosts_duplicates_preserves_comments() -> None:
    from shimkit.tools.ssh.scanner import prune_known_hosts_duplicates

    text = (
        "# header\n"
        "host1 ssh-ed25519 AAA1\n"
        "host1 ssh-ed25519 AAA1\n"  # dup
        "\n"
        "host2 ssh-rsa BBB2\n"
    )
    new, removed = prune_known_hosts_duplicates(text)
    assert removed == 1
    assert "# header" in new
    assert new.count("host1") == 1
    assert "host2" in new


def test_audit_perms_flags_world_readable_private_key(tmp_path: Path) -> None:
    from shimkit.tools.ssh.scanner import audit_perms

    tmp_path.chmod(0o700)
    priv = tmp_path / "id_ed25519"
    priv.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")
    priv.chmod(0o644)  # too lax
    issues = audit_perms(tmp_path)
    paths = [i.path for i in issues]
    assert priv in paths
    issue = next(i for i in issues if i.path == priv)
    assert issue.actual == "644" and issue.expected == "600"


def test_audit_perms_stricter_is_ok(tmp_path: Path) -> None:
    from shimkit.tools.ssh.scanner import audit_perms

    tmp_path.chmod(0o700)
    priv = tmp_path / "id_ed25519"
    priv.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")
    priv.chmod(0o400)  # stricter than 600 — fine
    issues = audit_perms(tmp_path)
    assert all(i.path != priv for i in issues)


# ─── manager: platform gating ───────────────────────────────────────────


def test_boot_exits_69_on_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.ssh.manager import SshManager

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Windows", machine="x86_64")),
    )
    with pytest.raises(SystemExit) as exc:
        SshManager.create().boot(ssh_dir_override=tmp_path)
    assert exc.value.code == 69


# ─── keys list ──────────────────────────────────────────────────────────


def test_keys_list_json_empty(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    result = runner.invoke(
        app, ["ssh", "keys", "list", "--ssh-dir", str(tmp_path), "--json"]
    )
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["keys"] == []


def test_keys_list_json_with_pair(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    (tmp_path / "id_ed25519").write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    )
    (tmp_path / "id_ed25519.pub").write_text(
        "ssh-ed25519 AAAA-pub u@h\n"
    )
    result = runner.invoke(
        app, ["ssh", "keys", "list", "--ssh-dir", str(tmp_path), "--json"]
    )
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert len(doc["data"]["keys"]) == 1
    assert doc["data"]["keys"][0]["name"] == "id_ed25519"
    assert doc["data"]["keys"][0]["type"] == "ed25519"


# ─── keys generate ──────────────────────────────────────────────────────


def test_keys_generate_invokes_ssh_keygen(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    captured: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        captured.append(list(cmd))
        # Simulate ssh-keygen creating the file so subsequent checks pass.
        if cmd[0] == "ssh-keygen":
            target = cmd[cmd.index("-f") + 1]
            Path(target).write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")
            Path(target + ".pub").write_text("ssh-ed25519 AAAA u@h\n")
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.ssh.manager.CommandRunner.run", staticmethod(fake_run)
    )
    result = runner.invoke(
        app,
        [
            "ssh",
            "keys",
            "generate",
            "id_test",
            "--ssh-dir",
            str(tmp_path),
            "--yes",
        ],
    )
    assert result.exit_code == 0
    assert captured and captured[0][0] == "ssh-keygen"
    assert "-t" in captured[0] and "ed25519" in captured[0]


def test_keys_generate_refuses_overwrite(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    (tmp_path / "id_test").write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    )
    result = runner.invoke(
        app,
        ["ssh", "keys", "generate", "id_test", "--ssh-dir", str(tmp_path), "--yes"],
    )
    assert result.exit_code == 1
    assert "already exists" in result.stdout


def test_keys_generate_dry_run_does_not_invoke_keygen(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    captured: list[list[str]] = []

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        captured.append(list(cmd))
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.ssh.manager.CommandRunner.run", staticmethod(fake_run)
    )
    result = runner.invoke(
        app,
        [
            "ssh",
            "keys",
            "generate",
            "id_test",
            "--ssh-dir",
            str(tmp_path),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert all(c[0] != "ssh-keygen" for c in captured)


# ─── keys rotate ────────────────────────────────────────────────────────


def test_keys_rotate_backs_up_and_regenerates(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    priv = tmp_path / "id_test"
    pub = tmp_path / "id_test.pub"
    priv.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nold\n")
    pub.write_text("ssh-ed25519 OLD u@h\n")

    def fake_run(cmd, **_):  # type: ignore[no-untyped-def]
        if cmd[0] == "ssh-keygen":
            target = cmd[cmd.index("-f") + 1]
            Path(target).write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nnew\n")
            Path(target + ".pub").write_text("ssh-ed25519 NEW u@h\n")
        return CommandResult(0, "", "")

    monkeypatch.setattr(
        "shimkit.tools.ssh.manager.CommandRunner.run", staticmethod(fake_run)
    )
    result = runner.invoke(
        app,
        ["ssh", "keys", "rotate", "id_test", "--ssh-dir", str(tmp_path), "--yes"],
    )
    assert result.exit_code == 0
    # Old key was backed up.
    backups = list(tmp_path.glob("id_test.bak-*"))
    assert backups, "expected an id_test.bak-* file"
    # New key written under the original name.
    assert priv.exists()
    assert "new" in priv.read_text()


# ─── agent ──────────────────────────────────────────────────────────────


def test_agent_status_reports_no_agent(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.ssh.manager.CommandRunner.run",
        staticmethod(
            lambda _cmd, **_: CommandResult(2, "", "Could not open a connection.")
        ),
    )
    result = runner.invoke(app, ["ssh", "agent", "status", "--json"])
    assert result.exit_code == 1
    doc = json.loads(result.stdout)
    assert doc["data"]["agent_running"] is False


def test_agent_status_reports_loaded_keys(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        "shimkit.tools.ssh.manager.CommandRunner.run",
        staticmethod(
            lambda _cmd, **_: CommandResult(
                0, "256 SHA256:fp1 user@host (ED25519)\n", ""
            )
        ),
    )
    result = runner.invoke(app, ["ssh", "agent", "status", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["keys_loaded"] == 1


# ─── known_hosts ────────────────────────────────────────────────────────


def test_known_hosts_audit_clean(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    (tmp_path / "known_hosts").write_text(
        "host1 ssh-ed25519 AAA1\nhost2 ssh-rsa BBB2\n"
    )
    result = runner.invoke(
        app,
        ["ssh", "known-hosts", "audit", "--ssh-dir", str(tmp_path), "--json"],
    )
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["duplicates"] == []


def test_known_hosts_prune_removes_duplicates(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    kh = tmp_path / "known_hosts"
    kh.write_text(
        "host1 ssh-ed25519 AAA1\nhost1 ssh-ed25519 AAA1\nhost2 ssh-rsa BBB2\n"
    )
    result = runner.invoke(
        app,
        ["ssh", "known-hosts", "prune", "--ssh-dir", str(tmp_path), "--yes"],
    )
    assert result.exit_code == 0
    body = kh.read_text()
    assert body.count("host1") == 1
    assert "host2" in body


# ─── perms ─────────────────────────────────────────────────────────────


def test_perms_audit_flags_loose_key(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    tmp_path.chmod(0o700)
    priv = tmp_path / "id_ed25519"
    priv.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")
    priv.chmod(0o644)
    result = runner.invoke(
        app, ["ssh", "perms", "audit", "--ssh-dir", str(tmp_path), "--json"]
    )
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert any(
        Path(i["path"]) == priv and i["expected"] == "600"
        for i in doc["data"]["issues"]
    )


def test_perms_fix_chmods_offenders(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    tmp_path.chmod(0o700)
    priv = tmp_path / "id_ed25519"
    priv.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")
    priv.chmod(0o644)
    result = runner.invoke(
        app, ["ssh", "perms", "fix", "--ssh-dir", str(tmp_path), "--yes"]
    )
    assert result.exit_code == 0
    mode = stat.S_IMODE(os.stat(priv).st_mode)
    assert mode == 0o600


def test_perms_fix_dry_run_does_not_chmod(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    tmp_path.chmod(0o700)
    priv = tmp_path / "id_ed25519"
    priv.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")
    priv.chmod(0o644)
    result = runner.invoke(
        app,
        ["ssh", "perms", "fix", "--ssh-dir", str(tmp_path), "--dry-run"],
    )
    assert result.exit_code == 0
    mode = stat.S_IMODE(os.stat(priv).st_mode)
    assert mode == 0o644  # unchanged


# ─── moderate prompt ────────────────────────────────────────────────────


def test_keys_generate_refuses_under_no_input(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    result = runner.invoke(
        app,
        [
            "ssh",
            "--no-input",
            "keys",
            "generate",
            "id_test",
            "--ssh-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "Cancelled" in result.stdout or "Pass --yes" in result.stdout
