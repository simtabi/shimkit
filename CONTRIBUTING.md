# Contributing to shimkit

Thanks for your interest. This file documents the project conventions
referenced from `README.md`.

## Development setup

```bash
git clone https://github.com/simtabi/shimkit
cd shimkit
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check src tests
mypy src/shimkit
bandit -r src/shimkit -ll
pip-audit --skip-editable
```

CI runs the same gates on macOS + Ubuntu × Python 3.10/3.11/3.12/3.13.
All must be green on every PR.

### Pre-commit hooks (recommended)

The same gates run pre-commit so PRs land without surprises:

```bash
pip install pre-commit
pre-commit install
```

The default hooks run `ruff`, `ruff-format`, `shellcheck`, file-format
checks, and trailing-whitespace cleanup. `mypy` is gated to the
``manual`` stage (it's too slow for every commit); run it explicitly:

```bash
pre-commit run --hook-stage manual mypy
```

### Optional tool extras

Each new tool has an optional dependency extra so the base install
stays lean. To work on a specific tool, install its extra:

```bash
pip install -e ".[dev,adguard]"        # ruamel.yaml + requests + psutil
pip install -e ".[dev,docker-clean]"   # docker SDK
pip install -e ".[dev,extra-tools]"    # everything
```

## Architecture rules

These are load-bearing — break them and a future tool will diverge from
the rest of the kit in ways that are hard to recover from.

1. **Every tool builds on `shimkit.core` primitives.** Do not re-implement
   subprocess execution, OS detection, package-manager dispatch, shell
   detection, rc-file writing, terminal output, or interactive prompts.
   If `shimkit.core` is missing what you need, extend it — don't fork it
   inside a tool.

2. **`CommandRunner.run` is the only place that calls `subprocess`.** This
   is the audit chokepoint. If you find yourself reaching for `subprocess`
   directly, route it through `CommandRunner` instead. Tests mock at this
   layer.

3. **Config values come from `shimkit.config.get_config()`.** Class-level
   constants for user-facing data (supported versions, search paths,
   command templates, colour toggles, repo URLs) belong in
   `src/shimkit/config/defaults.json` and the pydantic schema. Add the
   field to `schema.py`, populate `defaults.json`, regenerate
   `config/shimkit.schema.json`, and read it from `get_config()`.

4. **Logic-critical strings stay in code.** Idempotency markers (e.g.
   `# java-manager:openjdk@21`), regex patterns, and atomic-replace
   semantics must NOT be config-driven — a user changing the marker
   would corrupt their existing rc files. The line: if changing the
   value could break existing on-disk state, it's not config.

5. **Builder pattern for orchestrators.** Every tool's top-level class
   follows `Tool.create().boot().run()`. `boot()` wires components and
   returns `self`; `run()` is the interactive menu. Non-interactive
   subcommands call methods like `install(version)`, `list_things()` —
   never the menu.

6. **Fluent contracts return `self`.** Methods like
   `Shell.ensure_config_exists()`, `ShellConfigWriter.write_java_env()`,
   `UI.success()` (etc.) return their receiver so callers can chain.

## Adding a new tool

1. Create `src/shimkit/tools/<toolname>/` with `__init__.py`,
   `models.py`, the tool's domain classes, `manager.py` for the
   orchestrator, and `commands.py` for the Typer surface.
2. Add a section under `tools` in `src/shimkit/config/schema.py` and
   defaults in `src/shimkit/config/defaults.json`. Regenerate
   `config/shimkit.schema.json`.
3. Wire `app.add_typer(<toolname>_app)` in `src/shimkit/cli.py`.
4. Add `tests/test_tools_<toolname>.py` with at least: a `Manager.boot`
   smoke test, a CLI help test, a CLI exit-code propagation test.
5. Update `README.md` to add the new subcommand to the Tools section
   and the help block at the top.

A tool joins shimkit only if it shares ≥2 of `Platform` / `Shell` /
`PackageManager` / `UI` / `Menu`. Otherwise it's a separate package.

## Test conventions

- `tests/conftest.py` provides an autouse `_reset_env_and_config_cache`
  fixture and a `runner: CliRunner` fixture. Use them rather than
  re-rolling.
- For env or filesystem state: `monkeypatch.setenv` /
  `monkeypatch.delenv` / `tmp_path`. Tests must be hermetic against the
  developer's environment.
- For subprocess: stub `shimkit.core.CommandRunner.run` rather than
  reaching into `subprocess`. Tests that hit `subprocess` directly
  through a leaf module are signal that the module is bypassing the
  chokepoint.
- For pydantic config: write a JSON file under `tmp_path`, set
  `SHIMKIT_CONFIG=<path>`, then `reset_cache()`. The autouse fixture
  resets between tests so leakage isn't a concern.

## Releasing

See [`docs/release.md`](docs/release.md). Releases are
tag-driven; the `guard` job in `release.yml` will fail if the git tag
doesn't match `pyproject.toml`'s `project.version`.

## Style

- `ruff check` is authoritative. Don't argue with it — adjust the code.
- `mypy --strict` must pass. The pydantic plugin is configured; if
  you're hitting "Returning Any" errors, narrow the return at the
  source rather than `# type: ignore`-ing the call site.
- No comments that explain *what* the code does. Names should do that.
  Comments are for *why* — non-obvious constraints, workarounds, or
  references to issues. `# Phase X says…` migration references must
  not survive into committed code.
- Default to no error-handling/fallback for cases that can't happen.
  Only validate at system boundaries. `CommandRunner` already catches
  everything from subprocess; trust it.
