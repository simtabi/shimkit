# shimkit dns

macOS DNS resolver recovery and diagnostics. Targets the "ping works,
browser doesn't" failure mode where macOS's `Network.framework`
resolver state is corrupted but `mDNSResponder`'s cache and the
underlying network are fine.

Ported from `shell-scripts/fixdns.sh`. The shell version had a handful
of bugs (BSD `grep -E '\d'` silent fallthrough, Wi-Fi-only assumption
on non-Wi-Fi services, `timeout(1)` not on stock macOS, multi-byte
spinner glitch) — all fixed in the port.

## Commands

| Command                              | Purpose                                                   |
|--------------------------------------|-----------------------------------------------------------|
| `shimkit dns`                        | Interactive menu.                                         |
| `shimkit dns diagnose`               | Read-only: resolver chain, active service, interference.  |
| `shimkit dns flush`                  | `dscacheutil -flushcache && killall -HUP mDNSResponder`.  |
| `shimkit dns fix`                    | 6-step escalation; stops at the first step that resolves. |
| `shimkit dns show`                   | Configured DNS servers for the active service.            |
| `shimkit dns set <ip>...`            | Set DNS for the active service.                           |
| `shimkit dns reset --confirm RESET`  | Reset to DHCP (severe — token required).                  |
| `shimkit dns test [domain...]`       | Resolve test domains via the system resolver.             |
| `shimkit dns profile list`           | Installed encrypted-DNS / configuration profiles.         |
| `shimkit dns rollback`               | Restore the most recent plist backup made by `fix`.       |
| `shimkit dns diagnostics export`     | Dump a diagnostic bundle for a support ticket.            |

Every command accepts the standard flags: `--dry-run`, `--json`,
`--quiet`, `--verbose`, `--log-file`, `--no-color`. See
[CLI standards](../../prompt.md#cli-design-standards-per-cligdev).

## Typical flows

### 1. Browser stops resolving DNS

```bash
shimkit dns diagnose            # confirm it's resolver state, not network
shimkit dns flush               # try the 80% case first
shimkit dns fix --stop-at 3     # if flush didn't fix it, escalate to step 3
```

### 2. Need a clean diagnostic before opening a ticket

```bash
shimkit dns diagnostics export --out ~/Desktop/dns.txt
```

### 3. A previous nuclear reset broke Wi-Fi credentials

```bash
shimkit dns rollback
```

## Configuration

```json
{
  "tools": {
    "dns": {
      "test_domains": ["google.com", "cloudflare.com"],
      "dns_servers": {
        "cloudflare": ["1.1.1.1", "1.0.0.1"],
        "google":     ["8.8.8.8", "8.8.4.4"]
      },
      "step_timeout_seconds": 5,
      "nuclear_confirm_token": "REGENERATE",
      "reset_confirm_token": "RESET",
      "backup_dir": "~/Library/Application Support/shimkit/dns-backups"
    }
  }
}
```

## Exit codes

| Code | Meaning                                                       |
|-----:|---------------------------------------------------------------|
|    0 | Success / no-op (already resolving).                          |
|    1 | Step ran but didn't resolve; or invalid input.                |
|   69 | Wrong platform (not macOS) / optional extra missing.          |
|   77 | sudo required but not granted.                                |
|  130 | Interrupted by SIGINT.                                        |

## Platform support

| Platform     | Supported          |
|--------------|--------------------|
| macOS (Apple Silicon + Intel) | ✓ |
| Linux / WSL  | ✗ (exits 69)       |
| Container    | ✗ (exits 69)       |

## Troubleshooting

- `dns diagnose` shows `Tailscale MagicDNS (100.100.100.100) present` —
  Tailscale's DNS is on. `tailscale set --accept-dns=false` or
  `tailscale debug rebind` often resolves resolver-state issues.
- `dns fix` keeps failing at step 4 — the interface power-cycle.
  Confirm the active service is Wi-Fi via `shimkit dns diagnose`; the
  port now correctly skips airport-power on Ethernet services.
- `dns flush` returns 77 — needs root. Rerun via `sudo`.

## Origin

This tool is the Python port of `shell-scripts/fixdns.sh`. The shell
version is removed.
