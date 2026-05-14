# Developer onboarding

A practical walkthrough for getting productive on `shimkit`. Read
`architecture.md` first for the design rationale; this file is the
how-do-I-do-X reference.

If you have an hour, do steps 1–4. The rest you can read when you
need them.

---

## 1. Setup (5 minutes)

```bash
git clone https://github.com/simtabi/shimkit
cd shimkit
git config user.email "<your-noreply@users.noreply.github.com>"
git config user.name  "<Your Name>"

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,extra-tools]"
pre-commit install

# Verify
pytest -q
ruff check src tests
mypy src/shimkit
shimkit version
shimkit doctor
```

`[dev]` pulls test/lint tooling. `[extra-tools]` pulls the optional
dependencies for `dns`, `adguard`, and `docker-clean` so you can
work on every tool without re-installing.

---

## 2. The 30-second mental model

```
shimkit  (Typer dispatcher, src/shimkit/cli.py)
   │
   ├── java          ──► tools/java/        ┐
   ├── shell         ──► tools/shell/       │
   ├── dns           ──► tools/dns/         │  every tool follows the
   ├── adguard       ──► tools/adguard/     │  same manager / commands /
   └── docker-clean  ──► tools/docker_clean/┘  models / helpers layout
                              │
                              └─► shimkit.core (shared primitives)
                                  │
                                  ├── CommandRunner   ──► subprocess (only here)
                                  ├── Platform        ──► OS / arch detection
                                  ├── UI              ──► terminal output (only here)
                                  ├── Menu            ──► interactive prompts
                                  ├── PackageManager  ──► brew / apt / dnf / ...
                                  ├── Shell           ──► rc-file writing
                                  ├── Systemd         ──► systemctl wrapper (Linux)
                                  ├── log             ──► JSONL FileHandler
                                  ├── json_event      ──► --json output schema
                                  └── cli_flags       ──► shared Typer Options
```

The most common pattern when reading a tool: open `manager.py`, find
the orchestrator class, follow `boot()` to see what it wires, then
read the named methods that the Typer subcommands in `commands.py`
call.

---

## 3. The five load-bearing rules (with grep recipes)

These are also in [architecture.md](architecture.md) and
[CONTRIBUTING.md](../CONTRIBUTING.md). The grep recipes here let you
confirm a violation isn't hiding before you submit a PR.

| Rule | One-line check |
|------|----------------|
| Subprocess only via `CommandRunner` | `grep -rn 'import subprocess\|from subprocess' src/shimkit/` → exactly one hit, in `core/command.py` |
| UI output only via `UI.*` | `grep -rnE 'typer\.echo\|typer\.secho\|^[[:space:]]*print\(' src/shimkit/` → empty (the prints inside `core/ui.py` and `core/menu.py` are the chokepoint owners) |
| Config values via `get_config()` | When you see a literal like `["bash", "zsh"]` in a tool, ask: would changing this require a release? If no, it belongs in `defaults.json`. |
| Builder pattern: `Tool.create().boot().run()` | Skim any tool's `commands.py`; every entry point starts with this chain. |
| Fluent contracts return `self` | `UI.header("X").success("Y").info("Z")` should be chainable. |

If you find a real violation in existing code: it's a bug. File an
issue or open a PR. The Phase 1 audit catches were `cli.py`'s 18
`typer.echo` calls, the `brew.install_self` shell interpolation, and
one bare `print()` in `tools/java/manager.py`.

---

## 4. Adding a new tool (the canonical recipe)

Use this checklist when porting an existing utility into shimkit, or
when a new tool emerges from a real internal need. A tool joins
shimkit only if it shares **≥ 2** of `Platform` / `Shell` /
`PackageManager` / `UI` / `Menu` — otherwise it should be its own
package.

### 4a. Scaffold the package

```bash
mkdir -p src/shimkit/tools/<name>
touch src/shimkit/tools/<name>/{__init__.py,models.py,manager.py,commands.py}
```

`tools/<name>/__init__.py` re-exports the public API:

```python
"""<name> — one-line tagline."""
from __future__ import annotations
from .manager import <Name>Manager

__all__ = ["<Name>Manager"]
```

`models.py` holds typed value objects (`@dataclass(frozen=True)` for
inputs; mutable `@dataclass` for outcomes). No business logic here.

`manager.py` is the orchestrator. Boilerplate:

```python
from __future__ import annotations
import sys
from collections.abc import Callable
from shimkit.core import UI, Menu, Platform, get_logger

_LOG = get_logger("<name>")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69
EX_NOPERM = 77


class <Name>Manager:
    def __init__(self) -> None:
        self._platform: Platform | None = None
        # ... any other lazily-wired components

    @classmethod
    def create(cls) -> <Name>Manager:
        return cls()

    def boot(self) -> <Name>Manager:
        self._platform = Platform.detect()
        if not self._platform.is_<expected_platform>:
            UI.error(f"shimkit <name> targets X. Detected: {self._platform.system}")
            sys.exit(EX_UNAVAILABLE)
        # Optional: check optional extras here, exit 69 if missing.
        return self

    # Non-interactive methods used by Typer subcommands.
    def do_thing(self, *, json_out: bool = False) -> int:
        ...
        return EX_OK

    # Interactive menu — `shimkit <name>` with no subcommand.
    def run(self) -> None:
        actions: list[tuple[str, Callable[[], object]]] = [
            ("Do thing", lambda: self.do_thing()),
            ("Exit", lambda: None),
        ]
        labels = [lbl for lbl, _ in actions]
        while True:
            choice = Menu.select("<name> — what would you like to do?", labels)
            if choice is None or choice == "Exit":
                UI.info("Goodbye!")
                return
            dispatch = dict(actions)
            handler = dispatch.get(choice)
            if handler:
                handler()
```

`commands.py` is the Typer subapp:

```python
from __future__ import annotations
import typer
from shimkit.core import UI, attach_file_handler, set_verbose
from shimkit.core.cli_flags import (
    COLOR, DRY_RUN, JSON_OUT, LOG_FILE, NO_COLOR, NO_INPUT,
    QUIET, VERBOSE, YES, FORCE,
)
from shimkit.core.menu import Menu

<name>_app = typer.Typer(
    name="<name>",
    help="One-line tool description (Linux / macOS).",
    no_args_is_help=False,
)


def _bootstrap(
    log_file: str | None,
    verbose: bool,
    quiet: bool,
    no_color: bool,
    color: str | None,
    no_input: bool,
) -> None:
    if verbose: set_verbose(True)
    if quiet:   UI.set_quiet(True)
    if log_file: attach_file_handler(log_file)
    if no_color: UI.set_color_mode("never")
    elif color:  UI.set_color_mode(color)
    if no_input: UI.set_no_input(True)


# Universal flags live on the callback so every subcommand inherits them
# without repeating the wiring on each `do-thing` signature.
@<name>_app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    quiet: bool = QUIET,
    verbose: bool = VERBOSE,
    log_file: str = LOG_FILE,
    no_color: bool = NO_COLOR,
    color: str = COLOR,
    no_input: bool = NO_INPUT,
) -> None:
    _bootstrap(log_file, verbose, quiet, no_color, color, no_input)
    if ctx.invoked_subcommand is None:
        from .manager import <Name>Manager
        <Name>Manager.create().boot().run()


@<name>_app.command("do-thing")
def do_thing(
    json_out: bool = JSON_OUT,
    dry_run: bool = DRY_RUN,
    yes: bool = YES,
    force: bool = FORCE,
) -> None:
    """One-line description (shown in --help)."""
    # MODERATE-tier confirmation for non-trivial mutators. Short-circuits
    # on --yes / --force; refuses (rather than blocks) under --no-input.
    if not Menu.prompt_for_change(
        "This will mutate <thing>",
        yes=yes, force=force, no_input=UI.is_no_input(),
    ):
        raise typer.Exit(0)
    from .manager import <Name>Manager
    code = <Name>Manager.create().boot().do_thing(
        json_out=json_out, dry_run=dry_run
    )
    raise typer.Exit(code)
```

### 4b. Wire into the dispatcher

`src/shimkit/cli.py`:

```python
from shimkit.tools.<name>.commands import <name>_app
# ...
app.add_typer(<name>_app)
```

If your tool has a critical dependency that `shimkit doctor` should
surface, add a probe to the `doctor()` function (model the existing
`dns probe`, `adguard`, `docker` probes).

### 4c. Config schema (if needed)

In `src/shimkit/config/schema.py`, add a `_StrictModel` subclass and
add it to `ToolsConfig`:

```python
class <Name>Config(_StrictModel):
    some_setting: str = "default"
    timeout_seconds: int = Field(default=30, ge=1, le=300)


class ToolsConfig(_StrictModel):
    java: JavaConfig
    shell: ShellToolConfig
    # ... existing
    <name>: <Name>Config = Field(default_factory=<Name>Config)
```

In `src/shimkit/config/defaults.json`, add the section under
`tools.<name>`. Regenerate `config/shimkit.schema.json`:

```bash
.venv/bin/python -c "
import json
from shimkit.config.schema import ShimkitConfig
schema = ShimkitConfig.model_json_schema()
schema['\$schema'] = 'https://json-schema.org/draft/2020-12/schema'
schema['title'] = 'shimkit configuration'
print(json.dumps(schema, indent=2, ensure_ascii=False))
" > config/shimkit.schema.json
```

### 4d. Optional dependency extra (if needed)

If your tool depends on something heavier than the base install,
declare an extra in `pyproject.toml`:

```toml
[project.optional-dependencies]
<name>       = ["some-dep>=1.0"]
extra-tools  = [..., "some-dep>=1.0"]   # add to the umbrella
```

In your manager's `boot()`, check for the extra:

```python
def _require_optional_extras() -> bool:
    try:
        import some_dep  # noqa: F401
    except ImportError:
        UI.error("shimkit <name> needs `some-dep`. Install with:\n"
                 "  uv tool install 'shimkit[<name>]'")
        return False
    return True
```

### 4e. Tests

`tests/test_tools_<name>.py`, minimum coverage:

- `boot()` succeeds with mocked `Platform`.
- `boot()` exits 69 on wrong platform.
- `boot()` exits 69 when the optional extra is missing.
- Every non-interactive subcommand: one success path, one failure
  path, asserted exit codes.
- CLI `--help` lists every subcommand.
- `--json` mode emits parseable JSON for at least one command.
- `--dry-run` makes no destructive calls (assert via monkeypatch).
- Severe-tier ops abort without `--confirm <token>`.
- MODERATE-tier ops prompt `[y/N]` by default, skip on `--yes` /
  `--force`, and refuse with **exit 1** under `--no-input` or
  non-TTY stdin so scripts that intended to mutate don't silently
  succeed without doing anything.

Mock at `shimkit.core.CommandRunner.run`, `Platform(...)`, and the
tool-specific external libraries (`docker.from_env`, `requests`,
`psutil.net_connections`, …). NEVER touch a real daemon.

### 4f. Docs

`docs/tools/<name>.md`, following the template in
`docs/tools/{dns,adguard,docker-clean}.md`:

- Tagline
- Commands table (subcommand + one-line description)
- Typical flows (3–5 numbered example sessions)
- Configuration section (JSON snippet of the new keys)
- Exit codes table
- Platform support matrix
- Troubleshooting (3–5 common failures + the `doctor` output that
  indicates each)
- Origin note (if it's a port of something)

Cross-link from `docs/README.md` and `README.md`.

### 4g. CHANGELOG

Add to the `[Unreleased]` section under `Added`.

---

## 5. Common dev tasks

### Run a single test file

```bash
pytest tests/test_tools_dns.py -q
```

### Run with coverage and missing-line output

```bash
pytest -q --cov=shimkit --cov-report=term-missing
```

### Run only the security gates

```bash
bandit -r src/shimkit -ll
pip-audit --skip-editable
```

### Rebuild the JSON schema after editing `schema.py`

The recipe is in [step 4c above](#4c-config-schema-if-needed).

### Test a built wheel

```bash
python -m build
python -m venv /tmp/test-venv
/tmp/test-venv/bin/pip install dist/*.whl
/tmp/test-venv/bin/shimkit doctor
rm -rf /tmp/test-venv
```

### Try a tool in `--json` mode end-to-end

```bash
shimkit dns diagnose --json | jq .
shimkit docker-clean status --json | jq .data.disk
```

### See what changed in a specific source file across the project's
history

```bash
git log --follow --oneline -p -- src/shimkit/core/pkgmgr.py
```

---

## 6. Debugging common issues

### "Coverage fell below the floor"

Run locally with `pytest -q --cov=shimkit --cov-fail-under=65 --cov-report=term-missing`
to see which lines you didn't cover. The CI floor is documented in
the `test` job of `.github/workflows/ci.yml`; bump it when the
baseline rises.

### "Bandit says shell=True is dangerous"

Every `shell=True` in `src/shimkit/` has a `# nosec` annotation with
a one-line justification at the call site. If you add a new
`shell=True` without a justified `# nosec`, bandit fails the build.
Prefer the argv-list form.

### "Tests pass locally but fail in CI"

The most likely cause: a test depends on host state that CI doesn't
have. The conftest autouse fixture clears `SHIMKIT_CONFIG`,
`XDG_CONFIG_HOME`, and `NO_COLOR`, but it doesn't clear arbitrary
env vars or the real filesystem. If your test reads `/etc/*` or
`/proc/*`, monkeypatch the path resolution.

### "Manager.boot() exits 69 in tests"

You're missing a `monkeypatch.setattr(Platform, "detect", ...)`
call. See `_stub_macos` in `tests/test_tools_dns.py` or
`_stub_linux_install` in `tests/test_tools_adguard.py`.

### "ruff is complaining about `typer.Argument(...)` in defaults"

You shouldn't see this — `pyproject.toml` configures ruff's
`extend-immutable-calls` to allow `typer.Argument` and
`typer.Option` in argument defaults. If you do see B008, confirm
your local `pyproject.toml` matches `main`.

---

## 7. The CI gate map (mental model)

When you push, this is what runs in parallel:

```
test               ← matrix: 2 OS × 4 Python = 8 jobs. ruff + mypy + pytest.
security           ← bandit -ll + pip-audit. Fails on medium+.
build              ← sdist + wheel. Artifact uploaded.
smoke              ← install built wheel on macOS + Ubuntu, run CLI.
adguard-integration ← real AGH on ubuntu-latest. JSON-asserted output.
adguard-mutating-integration ← real `shimkit adguard fix` inside a privileged systemd container.
```

All must pass before merge to `main` (once branch protection is
configured — see `docs/shipping-checklist.md` row 1.8).

The release workflow only triggers on `v*` tags. Pushing to `main`
is a no-op for releases.

---

## 8. Where to ask questions

- File an issue on the GitHub repo.
- Re-read [architecture.md](architecture.md) — most "should I…?"
  questions are answered by the rules and patterns there.
- For validation-scope questions ("is this thing tested?"), see
  [validation-scope.md](validation-scope.md).
- For "what's left to ship?" questions, see
  [shipping-checklist.md](shipping-checklist.md).
