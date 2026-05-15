"""Coverage for ssh/scanner — pure parsing helpers.

These functions parse `ssh-add -L/-l`, `~/.ssh` contents, and
known_hosts; mostly string-in / structure-out so we test them
without any subprocess plumbing.
"""

from __future__ import annotations

from pathlib import Path

from shimkit.tools.ssh import scanner as _sc

# ─── parse_agent_keys (-l form) ────────────────────────────────────────


def test_parse_agent_keys_l_form_with_type() -> None:
    out = _sc.parse_agent_keys(
        "256 SHA256:abcDEF user@host (ED25519)\n"
        "3072 SHA256:xyz comment-only-no-paren (RSA)\n"
    )
    assert len(out) == 2
    assert out[0]["type"] == "ED25519"
    assert out[0]["fingerprint"] == "SHA256:abcDEF"
    assert out[0]["comment"] == "user@host"
    assert out[1]["type"] == "RSA"


def test_parse_agent_keys_l_form_no_paren() -> None:
    out = _sc.parse_agent_keys("256 SHA256:abc user@host\n")
    assert len(out) == 1
    # No parens → type unknown.
    assert out[0]["type"] == "?"
    assert out[0]["fingerprint"] == "SHA256:abc"


def test_parse_agent_keys_no_identities_short_circuits() -> None:
    assert _sc.parse_agent_keys("The agent has no identities.") == []


def test_parse_agent_keys_skips_blank_and_comment() -> None:
    out = _sc.parse_agent_keys("\n# a comment\n256 SHA256:fp host (ED25519)\n")
    assert len(out) == 1


# ─── parse_known_hosts / prune_known_hosts_duplicates ──────────────────


def test_parse_known_hosts_skips_blank_and_comment() -> None:
    text = "\n# comment\nexample.com ssh-rsa AAAA\nmal-formed-line\n"
    rows = _sc.parse_known_hosts(text)
    # Only the well-formed line.
    assert len(rows) == 1
    assert rows[0][1] == "example.com"


def test_prune_known_hosts_preserves_comments() -> None:
    text = (
        "# top comment\n"
        "example.com ssh-rsa AAAA\n"
        "example.com ssh-rsa AAAA\n"  # duplicate to be pruned
        "\n"
        "other.com ssh-ed25519 BBBB\n"
    )
    new, removed = _sc.prune_known_hosts_duplicates(text)
    assert removed == 1
    assert new.count("example.com ssh-rsa AAAA") == 1
    assert "# top comment" in new
    assert "other.com" in new


def test_prune_known_hosts_keeps_malformed() -> None:
    text = "malformed\nexample.com ssh-rsa A\nexample.com ssh-rsa A\n"
    new, removed = _sc.prune_known_hosts_duplicates(text)
    assert "malformed" in new
    assert removed == 1


# ─── expected_mode_for ───────────────────────────────────────────────


def test_expected_mode_for_paths(tmp_path: Path) -> None:
    perms = {
        "dir": "700",
        "config": "644",
        "known_hosts": "644",
        "authorized_keys": "644",
        "public_key": "644",
        "private_key": "600",
    }
    d = tmp_path / "dir"
    d.mkdir()
    assert _sc.expected_mode_for(d, perms) == "700"

    cfg = tmp_path / "config"
    cfg.write_text("")
    assert _sc.expected_mode_for(cfg, perms) == "644"

    kh = tmp_path / "known_hosts"
    kh.write_text("")
    assert _sc.expected_mode_for(kh, perms) == "644"

    auth = tmp_path / "authorized_keys"
    auth.write_text("")
    assert _sc.expected_mode_for(auth, perms) == "644"

    pub = tmp_path / "id.pub"
    pub.write_text("")
    assert _sc.expected_mode_for(pub, perms) == "644"

    priv = tmp_path / "id"
    priv.write_text("")
    assert _sc.expected_mode_for(priv, perms) == "600"


# ─── _check_one / audit_perms tree-walk ──────────────────────────────


def test_audit_perms_walks_dir_and_files(tmp_path: Path) -> None:
    """audit_perms walks ~/.ssh and flags loose modes — exercise tree
    walk including subdir + known_hosts + authorized_keys + pub + priv."""
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir(mode=0o700)
    sub = ssh_dir / "old_keys"
    sub.mkdir(mode=0o755)  # too lax for a dir
    (ssh_dir / "config").write_text("")
    (ssh_dir / "config").chmod(0o644)
    (ssh_dir / "known_hosts").write_text("")
    (ssh_dir / "known_hosts").chmod(0o644)
    (ssh_dir / "authorized_keys").write_text("")
    (ssh_dir / "authorized_keys").chmod(0o644)
    (ssh_dir / "id_ed25519.pub").write_text("ssh-ed25519 X user@host")
    (ssh_dir / "id_ed25519.pub").chmod(0o644)
    (ssh_dir / "id_ed25519").write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n"
    )
    (ssh_dir / "id_ed25519").chmod(0o666)  # too lax for private key

    issues = _sc.audit_perms(
        ssh_dir,
        perms_dir="700",
        perms_private="600",
        perms_public="644",
        perms_known="644",
        perms_authorized="644",
        perms_config="644",
    )
    paths = {str(i.path) for i in issues}
    # Subdir 0o755 should be flagged.
    assert any("old_keys" in p for p in paths)
    # Private key 0o666 should be flagged.
    assert any("id_ed25519" in p and not p.endswith(".pub") for p in paths)


def test_audit_perms_missing_ssh_dir_returns_empty(tmp_path: Path) -> None:
    """When ~/.ssh doesn't exist, the audit returns []."""
    issues = _sc.audit_perms(
        tmp_path / "absent",
        perms_dir="700",
        perms_private="600",
        perms_public="644",
        perms_known="644",
        perms_authorized="644",
        perms_config="644",
    )
    assert issues == []


# ─── _looks_like_private_key fast-paths ──────────────────────────────


def test_looks_like_private_key_skips_pub(tmp_path: Path) -> None:
    p = tmp_path / "id.pub"
    p.write_text("ssh-ed25519 AAAA")
    assert _sc._looks_like_private_key(p) is False


def test_looks_like_private_key_openssh(tmp_path: Path) -> None:
    p = tmp_path / "id"
    p.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nbody")
    assert _sc._looks_like_private_key(p) is True


def test_looks_like_private_key_rsa(tmp_path: Path) -> None:
    p = tmp_path / "id_rsa"
    p.write_text("-----BEGIN RSA PRIVATE KEY-----\nbody")
    assert _sc._looks_like_private_key(p) is True


def test_looks_like_private_key_random_file(tmp_path: Path) -> None:
    p = tmp_path / "notakey"
    p.write_text("totally not a key\n")
    assert _sc._looks_like_private_key(p) is False


def test_looks_like_private_key_unreadable(tmp_path: Path) -> None:
    """When read fails, returns False."""
    p = tmp_path / "ghost"
    # Don't create — non-existent file → OSError.
    assert _sc._looks_like_private_key(p) is False


# ─── list_keys edges ─────────────────────────────────────────────────


def test_list_keys_missing_dir(tmp_path: Path) -> None:
    assert _sc.list_keys(tmp_path / "nope") == []


def test_list_keys_handles_pub_without_private(tmp_path: Path) -> None:
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    # Just a .pub with no matching private key — list_keys ignores it.
    (ssh_dir / "stranger.pub").write_text("ssh-ed25519 AAAA")
    keys = _sc.list_keys(ssh_dir)
    assert keys == []


def test_list_keys_with_known_name_no_header(tmp_path: Path) -> None:
    """A file named id_ed25519 without a real header still counts."""
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    (ssh_dir / "id_ed25519").write_text("not really a key body")
    keys = _sc.list_keys(ssh_dir)
    assert len(keys) == 1
    assert keys[0].key_type == "ed25519"  # Inferred from name.


def test_key_type_from_name_rsa() -> None:
    assert _sc._key_type_from_name("id_rsa") == "rsa"


def test_key_type_from_name_ecdsa() -> None:
    assert _sc._key_type_from_name("id_ecdsa_sk") == "ecdsa"


def test_key_type_from_name_dsa() -> None:
    assert _sc._key_type_from_name("id_dsa") == "dsa"


def test_key_type_from_name_unknown() -> None:
    assert _sc._key_type_from_name("totally_unfamiliar") == "?"


def test_read_pub_metadata_too_short(tmp_path: Path) -> None:
    p = tmp_path / "id.pub"
    p.write_text("just-one-token")
    out = _sc._read_pub_metadata(p)
    assert out == ("?", None)


def test_read_pub_metadata_ecdsa_normalised(tmp_path: Path) -> None:
    p = tmp_path / "id.pub"
    p.write_text("ecdsa-sha2-nistp256 AAAA user@host")
    key_type, comment = _sc._read_pub_metadata(p)
    assert key_type == "ecdsa"
    assert comment == "user@host"


def test_read_pub_metadata_no_comment(tmp_path: Path) -> None:
    p = tmp_path / "id.pub"
    p.write_text("ssh-ed25519 AAAA")
    key_type, comment = _sc._read_pub_metadata(p)
    assert key_type == "ed25519"
    assert comment is None


def test_read_pub_metadata_unreadable(tmp_path: Path) -> None:
    assert _sc._read_pub_metadata(tmp_path / "ghost") == ("?", None)
