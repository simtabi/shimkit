# Version constraints — spec

> Per Phase 3.2 of the migration task. The system declares "this
> shimkit feature needs `docker ≥ 20.10`" once, in config, and
> enforces it at three points (install docs, runtime preflight,
> `shimkit doctor`) with three distinct outcomes when violated.

## Goals

1. One source of truth for version requirements (JSON config).
2. SemVer-aware comparison via `packaging.version.Version` — no
   home-rolled regex parsing.
3. Detection strategy declared **per tool** so the registry stays
   small and additive.
4. Three enforcement points consult the same registry:
   - install-time docs (rendered from config)
   - runtime preflight (`Manager.boot()`)
   - on-demand audit (`shimkit doctor`)
5. Four distinct outcomes with distinct exit / log behavior: **OK /
   OUT_OF_RANGE / MISSING / UNPARSEABLE**. None of them is "shimkit
   crashes the user's terminal".

## Non-goals

- Locking arbitrary user-installed package versions (out of scope).
- Auto-installing missing tools (every tool's own install method
  varies; we surface the install command, not run it).
- Cross-tool dependency resolution (treat each tool's constraint
  independently).

## Config schema

Under `tools.versions`:

```jsonc
{
  "tools": {
    "versions": {
      // Every key is optional. Absence means "no constraint" for
      // that tool. The detector still runs (so doctor can report
      // "you have docker 24.0.1") — only enforcement skips.
      "docker": { "min": "20.10", "max": "<25.0", "preferred": "24" },
      "nginx":  { "min": "1.20",  "max": null,    "preferred": null },
      "git":    { "min": "2.30",  "max": null,    "preferred": null },
      "gpg":    { "min": "2.2",   "max": null,    "preferred": null },
      "python": { "min": "3.10",  "max": "<4.0",  "preferred": "3.12" }
    }
  }
}
```

`min` / `max` / `preferred` accept:

- A bare version like `"20.10"` — treated as `>=` for `min`, `<=` for
  `max`, and informational for `preferred`.
- An explicit operator: `"<25.0"`, `"<=25.0"`, `">25.0"`, `">=25.0"`.
  Anything else is a config error.
- `null` or absence — "no bound".

`preferred` is purely informational (`shimkit doctor` may suggest an
upgrade if `version < preferred`).

## Detection registry

Each known tool has a detector. Pure functions of subprocess output:

```python
# core/version.py — sketch
_DETECTORS: dict[str, Detector] = {
    "docker": Detector(
        argv=["docker", "version", "--format", "{{.Server.Version}}"],
        parse=lambda out: out.strip() or None,
    ),
    "nginx": Detector(
        argv=["nginx", "-v"],
        # nginx prints to stderr: "nginx version: nginx/1.27.0"
        parse=lambda out, err: _re_search(r"nginx/([\d.]+)", err or out),
    ),
    "git": Detector(
        argv=["git", "--version"],
        parse=lambda out: _re_search(r"git version ([\d.]+)", out),
    ),
    "gpg": Detector(
        argv=["gpg", "--version"],
        parse=lambda out: _re_search(r"^gpg \(GnuPG\)[^\d]+([\d.]+)", out, multiline=True),
    ),
    "python": Detector(
        argv=[sys.executable, "--version"],
        parse=lambda out: _re_search(r"Python ([\d.]+)", out),
    ),
    # Add new tools here as new shimkit features depend on them.
}
```

Detectors run via `CommandRunner.run` (Rule 2 compliance). Their
output is fed to `packaging.version.parse()`:

- Parse success → `ToolVersion(name=..., version=<Version>, raw=...)`
- Parse failure → `ToolVersion(name=..., version=None, raw=...)` →
  status `UNPARSEABLE`.
- Detector exit non-zero or `argv[0]` not on PATH → `None` → status
  `MISSING`.

## Comparison

```python
from packaging.version import Version
from packaging.specifiers import SpecifierSet

def check(c: VersionConstraint, v: Version) -> Status:
    spec_parts: list[str] = []
    if c.min: spec_parts.append(_normalize(c.min, default_op=">="))
    if c.max: spec_parts.append(_normalize(c.max, default_op="<="))
    if not spec_parts:
        return Status.OK
    spec = SpecifierSet(",".join(spec_parts))
    return Status.OK if v in spec else Status.OUT_OF_RANGE
```

`_normalize` accepts bare versions (`"20.10"` → `">=20.10"`) and
explicit specifiers (`"<25.0"` → `"<25.0"`).

## Enforcement: three points

### 1. Install-time documentation

`docs/installation.md` includes a generated table of every
`tools.versions.*` constraint. The table is built once when a release
is cut (a tiny helper script under `scripts/render_version_table.py`
that walks `defaults.json` and emits Markdown). No runtime cost.

### 2. Runtime preflight

Each `Manager.boot()` declares its required tools:

```python
class DbManager:
    REQUIRED_TOOLS = ("docker",)

    def boot(self) -> DbManager:
        version.preflight(self.REQUIRED_TOOLS)
        # ... existing boot logic
```

`preflight()` raises a typed `VersionViolation` exception with the
status. The shared exception-to-exit-code mapping turns:

- `OUT_OF_RANGE` → exit 69 (EX_UNAVAILABLE) by default. If the user
  passes `--force`, downgraded to a warning and the manager proceeds.
- `MISSING` → exit 69 with a remediation message that includes the
  install command from `pkgmgr` (`brew install docker` /
  `apt-get install docker.io` / etc.).
- `UNPARSEABLE` → MODERATE warning, proceed. (Don't brick the user
  if Docker changes its version-string format.)

### 3. `shimkit doctor`

Runs `validate_all()` (every detector in the registry) and prints a
table:

```
$ shimkit doctor
shimkit  0.5.0
python   3.12.7 (/Users/.../shimkit/.venv/bin/python)
system   Darwin 25.5.0 arm64
…
versions
  docker    24.0.7    ok      (min: 20.10, preferred: 24)
  nginx     1.27.0    ok      (min: 1.20)
  git       2.42.0    ok      (min: 2.30)
  gpg       2.4.5     ok      (min: 2.2)
  python    3.12.7    ok      (min: 3.10, preferred: 3.12)
```

With a violation:

```
versions
  docker    19.03.13  out-of-range  (need >=20.10; got 19.03.13)
                                    → install: brew install --cask docker
  nginx     missing                 (not on PATH)
                                    → install: brew install nginx
                                              apt install nginx
  unicorn   unparseable             (got "v???"; couldn't read version)
```

`--json` mode emits the same content as a structured `Event` with
`status` in {"ok", "warning", "error"}: warning when any constraint
is `OUT_OF_RANGE` / `UNPARSEABLE`, error when any required tool is
`MISSING`.

## Status enum, exit-code mapping, log behavior

| Status | Exit (preflight, without `--force`) | Exit (preflight, with `--force`) | Doctor outcome | JSONL `level` |
|--------|--------------------------------------|-----------------------------------|----------------|---------------|
| OK | 0 (continue) | 0 | (no entry needed) | n/a |
| OUT_OF_RANGE | 69 | 0 (warn-only) | warning row | WARNING |
| MISSING | 69 | 69 (force can't conjure a binary) | error row | ERROR |
| UNPARSEABLE | 0 (warn-only) | 0 | warning row | WARNING |

## API contracts

```python
# core/version.py — public surface
def detect(tool: str, *, runner: CommandRunner = CommandRunner) -> ToolVersion | None: ...
def constraint(tool: str) -> VersionConstraint:
    """Read the constraint for `tool` from `get_config().tools.versions`."""
def validate(tool: str) -> Result:
    """Run detect + check, return Result with status + ToolVersion + constraint."""
def validate_all() -> dict[str, Result]:
    """All known detectors. Used by `shimkit doctor`."""
def preflight(tools: Sequence[str], *, force: bool = False) -> None:
    """Raise VersionViolation if any tool fails. Wired into boot()."""
```

`Result` is a frozen dataclass `(status, tool_version, constraint,
remediation)`. `remediation` is a string sourced from `pkgmgr` for
the platform — `"brew install docker"` on macOS, etc.

## Testing strategy

`tests/test_core_version.py`:

- Pure parser tests for each detector's `parse=` lambda (fixtures of
  real CLI outputs captured offline).
- Constraint-check matrix: `(min, max, version)` → `Status`.
- Boot-time preflight: `MISSING` → exit 69; `OUT_OF_RANGE` → exit 69
  without `--force`, 0 with `--force`; `UNPARSEABLE` → 0.
- `shimkit doctor --json` shape with mixed statuses.

No real binaries invoked. `CommandRunner.run` monkeypatched
throughout.

## Migration impact

- New `core/version.py` module (~250 LOC).
- New `VersionConstraint` model in `config/schema.py` (~30 LOC).
- New `tools.versions` block in `defaults.json` for the tools shimkit
  itself currently depends on (`docker`, `git`, `gpg`, `nginx`,
  `python`).
- `shimkit doctor` extended to call `validate_all()` (~20 LOC).
- Each existing tool's `boot()` gains `version.preflight((...))`
  one-liner — strictly opt-in per tool, no implicit checks.

Total ≈ 350 LOC + 30 tests. Lands as the FIRST work item of v0.5.0
since every other adopt-list item depends on it (`shimkit db mysql`
preflights `docker`).
