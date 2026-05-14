# Validation scope

What shimkit's automated and manual validation covers — and what it
intentionally does not. Use this page to decide:

- Whether a new bug report falls inside our supported envelope.
- Whether a PR is allowed to ship without additional manual testing.
- What to write in the v0.2.0+ release PR description for each
  sign-off check.

The companion document is [`shipping-checklist.md`](shipping-checklist.md),
which tracks **release-blocking** items in dependency order.

---

## In scope

### Automated gates (run on every PR via `.github/workflows/ci.yml`)

| Gate | What it validates |
|------|-------------------|
| `test` (macOS + Ubuntu × Python 3.10/3.11/3.12/3.13) | Unit + CLI integration tests with mocked `CommandRunner`, `Platform`, `requests`, `psutil`, `Systemd`. Coverage floor enforced. |
| `security` | `bandit -ll` (SAST, fail on medium+) and `pip-audit --skip-editable` (CVE scan of resolved deps). |
| `dockerfile-hadolint` | `Dockerfile` is hadolint-clean. |
| `build` | `python -m build` produces a clean sdist + wheel. |
| `smoke` (macOS + Ubuntu) | Built wheel installs into a fresh venv. `shimkit --help`, `shimkit version`, `shimkit doctor` all exit 0; the three new sub-apps (`dns`, `adguard`, `docker-clean`) appear in root `--help`. |
| `adguard-integration` (Ubuntu) | Real AdGuard Home (version pinned in workflow) downloaded, run on non-default ports 5300/8000, then `shimkit adguard scan / verify / ports show / fix --dry-run / ports set --dry-run` invoked with JSON-asserted output. |

### Manual gates (run by the human releasing a new version)

Documented in [`prompt.md`](../prompt.md#phase-7--ubuntu-validation-v020-sign-off)
Phase 7. Headline items:

- `shimkit adguard fix` end-to-end on a real Ubuntu host with
  `systemd-resolved` and NetworkManager active. Verifies the
  systemd drop-in lands, `/etc/resolv.conf` is rewritten, the NM
  `dns=none` drop-in survives an interface event, and `rollback`
  restores both backups.
- `shimkit adguard ports set` yaml fallback when the AGH API is
  unreachable. Verifies the atomic edit, comment/order preservation
  via `ruamel.yaml`, and that AGH is stopped before the edit and
  restarted after.
- `shimkit docker-clean restart` through systemd on Linux (the
  path that the bash predecessor silently broke via `((attempt++))`
  under `set -e`).

---

## Out of scope (deliberate)

These are not bugs and not regressions. Reports against these are
either redirected to a different project or filed as feature
requests for future scope expansion.

### 1. Hostile-network scenarios

shimkit is a developer-productivity toolkit, not a network-security
audit subject. We do not validate behaviour under:

- DNS exfiltration filters or transparent DNS rewriters at the
  network edge.
- Captive portals that rewrite `/etc/resolv.conf` mid-session.
- Outbound HTTPS interception (corporate MITM proxies); the
  `Brew.install_self` and AdGuard API paths trust the system
  trust store and will refuse a self-signed cert by default.
- DNS rebinding, cache poisoning, or other active attacks against
  the user's own resolver.

The right tool for those scenarios is a dedicated network-security
suite. If you're operating in a hostile network, treat shimkit's
output as advisory and verify everything against a known-good
baseline.

### 2. Distros beyond Ubuntu 22.04 / 24.04

`shimkit adguard` is documented and validated for Ubuntu 22.04 LTS
and Ubuntu 24.04 LTS. Other Linux distributions (Debian, Fedora,
RHEL, Arch, Alpine, …) are **expected to work** because the
implementation only depends on:

- `systemd` (any 240+ release).
- `NetworkManager` when present (any 1.20+).
- `psutil` (Python; cross-distro).
- `ruamel.yaml` (Python; cross-distro).
- The AdGuard Home binary (statically linked; cross-distro).

…but we do not formally test on them. First-class support for any
new distro is its own follow-up:

| Distro | Status | Path to support |
|--------|--------|-----------------|
| Ubuntu 22.04 / 24.04 LTS | Supported | Validated in Phase 7 |
| Debian 12+ | Expected to work | File an issue if it doesn't; PR welcome |
| Fedora 40+ | Expected to work | Add a CI matrix row under `adguard-integration` |
| Arch Linux | Expected to work | Same |
| Alpine / openSUSE / RHEL | Expected to work | Same |
| WSL2 | **Not supported** | `systemd-resolved` and NetworkManager don't behave the way they do on bare Linux; the tool exits 69 |

If you want a new distro added to the supported list, open an
issue that includes:

1. A successful `shimkit adguard scan` and `shimkit adguard fix
   --dry-run` transcript on that distro.
2. The output of `lsb_release -a` and `systemctl --version`.
3. The output of `shimkit doctor`.

We'll add a CI matrix row.

### 3. CI does not exercise the `/etc/resolv.conf` rewrite path

The `adguard-integration` CI job runs AGH on non-default ports
(5300/8000) so it doesn't fight the ubuntu-latest runner's
`systemd-resolved`. This means CI exercises:

- ✅ The psutil port-scan
- ✅ The AGH HTTP control API (auth + status + configure)
- ✅ The `ruamel.yaml` read + atomic write paths
- ✅ The `fix --dry-run` decision tree
- ✅ The exit-code contracts for `verify`, `ports show`, `ports set --dry-run`

…but does **not** exercise:

- ❌ The `systemd-resolved` drop-in being written
- ❌ The `/etc/resolv.conf` symlink-or-static swap
- ❌ The `NetworkManager` `dns=none` drop-in
- ❌ The `fix` mutating path (real `systemctl stop AdGuardHome` →
  yaml edit → `systemctl start`)
- ❌ The `rollback` path

Those paths are exercised by Phase 7 manual validation on a real
Ubuntu desktop. Why this split:

- **Cost.** Spinning up a dedicated VM in CI just to exercise
  resolver rewrites would slow every PR by minutes.
- **Damage radius.** A test that rewrites `/etc/resolv.conf` on a
  shared GitHub-hosted runner has a non-zero chance of leaking
  state into subsequent jobs.
- **Realism.** The runner image is a synthetic environment. A bug
  that only shows up under "real systemd-resolved on a real
  desktop" is a bug we'd catch sooner with a single Phase-7 manual
  run than with a CI test that mocks half the system.

The trade-off is documented in [`prompt.md`](../prompt.md#phase-7--ubuntu-validation-v020-sign-off)
Phase 7 step 4 — the v0.2.0 sign-off PR description must record
each mutating path as PASS/FAIL/SKIP.

---

## Expanding scope

To add a new automated validation:

1. Identify the gap (an exit-code contract not asserted, a
   platform not covered, a flag combination not exercised).
2. Add a unit test if the gap can be expressed with mocks; an
   integration test if it needs a real daemon.
3. Wire the test into `.github/workflows/ci.yml` as a new job or
   matrix dimension.
4. Update the "In scope → Automated gates" table above.
5. If the addition closes an item in this page's "Out of scope"
   section, move it from one section to the other.

To add a new manual validation:

1. Add a numbered step to [`prompt.md`](../prompt.md) Phase 7.
2. Add a row to the sign-off criteria table.
3. Reference the new step in [`shipping-checklist.md`](shipping-checklist.md)
   if it's release-blocking.

---

## Related

- [`shipping-checklist.md`](shipping-checklist.md) — release-blocking
  items in dependency order.
- [`release.md`](release.md) — cutting a new version, the CI
  pipeline, what each release job does.
- [`tools/adguard.md`](tools/adguard.md) — the `shimkit adguard`
  tool docs, including platform support matrix.
- [`prompt.md`](../prompt.md) — the senior-engineering brief that
  drove the initial port; Phase 7 is the Ubuntu sign-off plan.
