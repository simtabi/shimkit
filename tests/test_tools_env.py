"""Tests for ``shimkit env``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shimkit.cli import app


def _force_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Linux", machine="x86_64")),
    )


# ─── pure parser ─────────────────────────────────────────────────────────


def test_parse_simple_kv() -> None:
    from shimkit.tools.env.parser import parse

    env = parse("APP_ENV=production\nLOG_LEVEL=info\n")
    entries = env.entries()
    assert len(entries) == 2
    assert entries[0].key == "APP_ENV" and entries[0].value == "production"
    assert entries[0].quoted is False


def test_parse_quoted_value_with_escapes() -> None:
    from shimkit.tools.env.parser import parse

    env = parse('MSG="hello\\nworld"\n')
    e = env.entries()[0]
    assert e.value == "hello\nworld"
    assert e.quoted is True


def test_parse_single_quoted_no_escape() -> None:
    from shimkit.tools.env.parser import parse

    env = parse("PATTERN='\\n'\n")
    e = env.entries()[0]
    # Single-quoted: literal backslash-n, not a newline.
    assert e.value == "\\n"


def test_parse_handles_export_prefix() -> None:
    from shimkit.tools.env.parser import parse

    env = parse("export FOO=bar\n")
    e = env.entries()[0]
    assert e.key == "FOO" and e.value == "bar"


def test_parse_preserves_comments_and_blanks() -> None:
    from shimkit.tools.env.parser import parse, render

    src = "# header\n\nAPP=ok\n"
    env = parse(src)
    assert render(env) == src


def test_parse_handles_trailing_comment() -> None:
    from shimkit.tools.env.parser import parse

    env = parse("HOST=localhost # the dev host\n")
    e = env.entries()[0]
    assert e.value == "localhost"
    assert e.comment == "the dev host"


def test_parse_invalid_key_is_preserved_as_raw() -> None:
    from shimkit.tools.env.parser import parse, render

    src = "1bad=val\n"
    env = parse(src)
    # No entries — invalid key.
    assert env.entries() == []
    # But the line is preserved verbatim on render.
    assert render(env) == src


def test_diff_keys_only_in_a_only_in_b_differ() -> None:
    from shimkit.tools.env.parser import diff_keys, parse

    a = parse("A=1\nB=2\nC=3\n")
    b = parse("B=99\nC=3\nD=4\n")
    d = diff_keys(a, b)
    assert d == {"only_a": ["A"], "only_b": ["D"], "differ": ["B"]}


def test_is_secret_key_case_insensitive() -> None:
    from shimkit.tools.env.parser import is_secret_key

    p = "password|secret|api[_-]?key"
    assert is_secret_key("DATABASE_PASSWORD", p)
    assert is_secret_key("api_key", p)
    assert is_secret_key("API-KEY", p)
    assert not is_secret_key("LOG_LEVEL", p)


def test_redact_value_caps_at_eight_chars() -> None:
    from shimkit.tools.env.parser import redact_value

    assert redact_value("") == ""
    assert redact_value("abc") == "***"
    assert redact_value("x" * 100) == "*" * 8


def test_render_redacted_masks_secrets() -> None:
    from shimkit.tools.env.parser import parse, render_redacted

    env = parse("APP_ENV=production\nAPI_KEY=supersecret123\n")
    out = render_redacted(env, pattern="password|secret|api[_-]?key|token")
    assert "production" in out
    assert "supersecret123" not in out
    assert "API_KEY=" in out


def test_render_redacted_with_reveal_shows_values() -> None:
    from shimkit.tools.env.parser import parse, render_redacted

    env = parse("API_KEY=supersecret123\n")
    out = render_redacted(env, pattern="api[_-]?key", reveal=True)
    assert "supersecret123" in out


# ─── manager: platform ───────────────────────────────────────────────────


def test_boot_exits_69_on_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    from shimkit.core.platform import Platform
    from shimkit.tools.env.manager import EnvManager

    monkeypatch.setattr(
        Platform,
        "detect",
        classmethod(lambda cls: Platform(system="Windows", machine="x86_64")),
    )
    with pytest.raises(SystemExit) as exc:
        EnvManager.create().boot()
    assert exc.value.code == 69


# ─── show ────────────────────────────────────────────────────────────────


def test_env_show_json_redacts_secrets(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    target = tmp_path / ".env"
    target.write_text("APP_ENV=production\nAPI_KEY=secret123\n")
    result = runner.invoke(app, ["env", "show", str(target), "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    entries = {e["key"]: e for e in doc["data"]["entries"]}
    assert entries["APP_ENV"]["value"] == "production"
    assert entries["API_KEY"]["redacted"] is True
    assert entries["API_KEY"]["value"] != "secret123"


def test_env_show_json_reveal_shows_secrets(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    target = tmp_path / ".env"
    target.write_text("API_KEY=secret123\n")
    result = runner.invoke(app, ["env", "show", str(target), "--reveal", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    e = doc["data"]["entries"][0]
    assert e["key"] == "API_KEY" and e["value"] == "secret123"
    assert e["redacted"] is False


def test_env_show_missing_path_returns_1(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    monkeypatch.chdir(tmp_path)  # cwd has no .env
    result = runner.invoke(app, ["env", "show"])
    assert result.exit_code == 1


# ─── list ────────────────────────────────────────────────────────────────


def test_env_list_finds_dotted_envs(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    (tmp_path / ".env").write_text("A=1\n")
    (tmp_path / ".env.local").write_text("A=2\n")
    (tmp_path / "ignore.txt").write_text("not env\n")
    # Build a subdir with a node_modules-style trap.
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / ".env").write_text("LIBRARY=1\n")
    result = runner.invoke(app, ["env", "list", str(tmp_path), "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    names = {Path(p).name for p in doc["data"]["files"]}
    assert ".env" in names and ".env.local" in names
    # node_modules pruned.
    assert all("node_modules" not in p for p in doc["data"]["files"])


# ─── scaffold ────────────────────────────────────────────────────────────


def test_env_scaffold_writes_template(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    target = tmp_path / ".env"
    result = runner.invoke(app, ["env", "scaffold", str(target)])
    assert result.exit_code == 0
    assert target.is_file()
    body = target.read_text()
    assert "APP_NAME=" in body and "API_KEY=" in body


def test_env_scaffold_refuses_overwrite(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    target = tmp_path / ".env"
    target.write_text("EXISTING=1\n")
    result = runner.invoke(app, ["env", "scaffold", str(target)])
    assert result.exit_code == 1
    assert "already exists" in result.stdout
    # Untouched.
    assert target.read_text() == "EXISTING=1\n"


def test_env_scaffold_dry_run_does_not_write(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    target = tmp_path / ".env"
    result = runner.invoke(app, ["env", "scaffold", str(target), "--dry-run"])
    assert result.exit_code == 0
    assert not target.exists()


# ─── diff ────────────────────────────────────────────────────────────────


def test_env_diff_reports_differences(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    a = tmp_path / "a.env"
    b = tmp_path / "b.env"
    a.write_text("X=1\nY=2\n")
    b.write_text("Y=99\nZ=3\n")
    result = runner.invoke(app, ["env", "diff", str(a), str(b), "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["data"]["only_a"] == ["X"]
    assert doc["data"]["only_b"] == ["Z"]
    assert doc["data"]["differ"] == ["Y"]


# ─── redact ──────────────────────────────────────────────────────────────


def test_env_redact_writes_masked_copy(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _force_linux(monkeypatch)
    src = tmp_path / ".env"
    dst = tmp_path / ".env.redacted"
    src.write_text("APP=ok\nDATABASE_PASSWORD=hunter2\n")
    result = runner.invoke(app, ["env", "redact", str(src), str(dst)])
    assert result.exit_code == 0
    body = dst.read_text()
    assert "hunter2" not in body
    assert "APP=ok" in body
