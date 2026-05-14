# Known issues and pending items

Things that don't quite work in CI, or that are deliberately deferred
for a future release. Tracked here so contributors and operators can
see what's known and decide if it matters for their use case.

For the release-blocking checklist see
[`shipping-checklist.md`](../shipping-checklist.md). For the broader
validation envelope see [`validation-scope.md`](../validation-scope.md).

---

## NM-honours-`dns=none`-on-real-interface-event — not automated

**What we don't test in CI.** The runtime property that
NetworkManager respects the `dns=none` directive (from
`/etc/NetworkManager/conf.d/90-shimkit-adguardhome.conf`) when a real
link event fires — Wi-Fi reconnect, Ethernet unplug, DHCP lease
renewal, VPN up/down, suspend/resume.

**What we DO test in CI** (`adguard-mutating-integration` job):

1. ✓ The drop-in lands at `/etc/NetworkManager/conf.d/90-shimkit-adguardhome.conf`.
2. ✓ The file body is `[main]\ndns=none\n` (asserted by `grep`).
3. ✓ `nmcli general reload` returns success — NM accepted the new config.

These are the **syntactic** correctness of the drop-in. The
**runtime** correctness (does NM actually leave `/etc/resolv.conf`
alone when the next link event fires?) is the missing piece.

### Why containers can't validate this

The check requires three things that simply don't exist inside a
container, including a privileged systemd one:

1. **A real, NM-managed network interface.** Containers only have
   `veth` pairs created by Docker. NetworkManager doesn't manage
   `veth` by default (`unmanaged-devices=type:veth` in its built-in
   defaults), and forcing it to would fight Docker's IPAM and break
   the container's network.

2. **A real link event.** Containers don't get them. There's no
   `wpa_supplicant`, no `dhclient`, no suspend/resume, no
   modem-manager state change. After Docker brings the `veth` up at
   container start, the interface stays in a single state for the
   container's lifetime. `nmcli connection up/down` against an
   unmanaged `veth` is a no-op.

3. **Observation across the event.** The shape of the bug we'd be
   guarding against is "NM clobbered `/etc/resolv.conf` despite
   `dns=none`" — and that only manifests when (1) and (2) co-occur.
   In a container we'd be reading a file NM never touched and
   concluding "drop-in works", which is the same conclusion you reach
   from `cat`-ing the static file content.

### Why we accept the residual risk

The runtime property is **upstream NetworkManager behaviour**, not
shimkit behaviour. The `dns=none` directive is documented in
`NetworkManager.conf(5)` as authoritative for "don't manage
`resolv.conf`":

> If set, NetworkManager will not modify resolv.conf. Effectively the
> resolv.conf related options become inaccessible to NetworkManager.

NM has shipped this directive since at least 2015 and tests it in
their own CI. The risk shimkit is carrying by not testing item 7
ourselves is **"will a future NM release regress `dns=none`?"** —
which would be a release-blocking upstream bug that NM would fix
immediately, and which would equally break every other DNS-manager
tool (pi-hole, AGH-CLI, Unbound's resolvconf integration, etc.).

The mitigation we've put in place: the v0.2.0+ `shimkit doctor`
command surfaces the NM service state, so a user investigating
flaky DNS post-fix can confirm in one command whether NM is the
active manager — pointing them at the right upstream issue if NM
behaviour has regressed.

### What would change this

Three plausible automation paths exist; none currently pay for
themselves given the residual risk profile.

| Approach | Cost | Confidence |
|----------|-----:|-----------:|
| KVM nested virt + a real Ubuntu VM in CI | High (GitHub `ubuntu-latest` doesn't expose KVM by default; needs the recently-added `ubuntu-22.04-arm` runners or a self-hosted setup) | High |
| Vagrant + VirtualBox in CI | Medium-high (slow, brittle, maintenance burden) | Medium |
| Lima/multipass on a self-hosted runner | High (out of scope for OSS without dedicated infrastructure) | High |

The bar for re-evaluating: if upstream NM regresses `dns=none` even
once, the cost-benefit flips and we'd add KVM-VM-based CI.

### Manual validation procedure

For maintainers cutting a release who want to verify item 7 on a
real Ubuntu desktop before tagging — the steps are in
[`prompt.md` Phase 7 step 2b](../../prompt.md#step-2--shimkit-adguard-mutating-path-validation).
The condensed version:

```bash
# After running shimkit adguard fix on a real Ubuntu host with NM active:
ls /etc/NetworkManager/conf.d/90-shimkit-adguardhome.conf
nmcli connection down "<your-wifi-or-ethernet-connection>"
nmcli connection up   "<your-wifi-or-ethernet-connection>"
readlink -f /etc/resolv.conf
cat /etc/resolv.conf | head -3
```

Expected: `/etc/resolv.conf` still points at `/run/systemd/resolve/
resolv.conf` (symlink mode) or still has `nameserver 127.0.0.1`
(static mode). Anything else means NM clobbered the file — file an
issue with the `nmcli general info` output and the contents of
`/etc/NetworkManager/conf.d/90-shimkit-adguardhome.conf`.

---

## Coverage gap to 85% — deferred

**Current:** 66% line coverage (CI floor 65%).
**Target:** 85% (per the v0.2.0 brief).
**Gap:** ~19 percentage points, mostly in:

- Interactive `Manager.run()` menu loops (`tools/{java,shell,dns,adguard,docker_clean}/manager.py`) — questionary-based, hard to test without deep `Menu` mocking that breaks when the menu UX evolves.
- Destructive code paths (`step_nuclear` in `dns/fixer.py`) — by design
  exercised only in manual smoke.
- The full `adguard fix` mutating path on real `/etc/*` — covered by
  the `adguard-mutating-integration` CI job, not by unit tests.

Pushing closer to 85% means ~80–100 mock-heavy tests of declining
marginal value. Recommend revisiting if `v0.3.0` adds significant
new logic in the affected paths.

---

## Optional: `gh attestation verify` smoke test

The release workflow signs the wheel and the container image with
`actions/attest-build-provenance@v3`. We don't currently have a CI
job that **verifies** those attestations after publish (the action
publishes them; nothing reads them back).

Low priority — Sigstore's transparency log is the authoritative
record. A post-publish verify job would catch a misconfiguration of
the publish flow, but the bug shape is rare and would be
release-blocking by other means (PyPI upload failures, GHCR push
failures, etc.) before the signature step.

If added: a `verify-release` job that runs after `publish-pypi` and
`publish-ghcr`, fetching the published artifacts and running
`gh attestation verify` against them.

---

## Lifecycle of this file

Entries land here when:

- A check is documented as in-scope but can't be automated for a
  concrete reason (containers, third-party hosting, cost).
- A target metric is deferred to a future release.
- An aspirational follow-up has a path but no owner.

Entries leave here when:

- The check moves into CI (move to `validation-scope.md` "In scope").
- The target is met (delete the entry; the new baseline is the
  baseline).
- The aspiration ships (delete; reference the CHANGELOG entry).
