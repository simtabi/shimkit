<!--
Thanks for your contribution! A few notes:

- Read CONTRIBUTING.md for the architecture rules — they're
  load-bearing. If your PR violates one, please flag it in the
  description so it can be discussed.
- Keep PRs focused. One concern per PR; bundled refactors get
  rejected more often than they get merged.
- ruff + mypy --strict + pytest must all pass. CI runs them on
  macOS + Ubuntu × Python 3.10/3.11/3.12/3.13.
-->

## What changed

<!-- One or two sentences. The "why" matters more than the "what". -->

## Why

<!-- Reference an issue, an external bug report, a user pain point.
     If this is a refactor, what's the motivation? -->

## Test plan

- [ ] `pytest -q` passes locally
- [ ] `ruff check src tests` clean
- [ ] `mypy src/shimkit` clean
- [ ] `shimkit doctor` smoke (paste the output if relevant)
- [ ] If config changed: regenerated `config/shimkit.schema.json`
- [ ] If a new tool: added smoke tests covering boot + help + exit codes
- [ ] If user-facing change: updated CHANGELOG.md

## Checklist

- [ ] My commit message follows the project's style (imperative, ≤72-char
      subject, blank line, then a brief why-block)
- [ ] I have not introduced subprocess calls outside `CommandRunner`
- [ ] I have not put logic-critical strings in config (markers, regexes,
      atomic-replace semantics stay in code)
- [ ] If I touched `Dockerfile`: image still builds (`docker build .`)
