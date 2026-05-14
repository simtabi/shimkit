# shimkit adguard

AdGuard Home port-conflict fixer for Linux. Frees the ports AGH needs
(53 / 80 / 443 / 3000) by handling `systemd-resolved`, NetworkManager,
known-safe DNS daemons (dnsmasq, bind, named, unbound), and pi-hole.

Ported from `shell-scripts/fix-adguardhome-ports.sh`. The shell version
ran a full DNS cleanup even when AGH was absent, awk-edited the yaml
while AGH was running, and only warned about NetworkManager — all
fixed in the port.

## Commands

| Command                                            | Purpose                                                          |
|----------------------------------------------------|------------------------------------------------------------------|
| `shimkit adguard`                                  | Interactive menu.                                                |
| `shimkit adguard scan`                             | List configured ports, owners, conflicts. Read-only.             |
| `shimkit adguard fix`                              | Remediate. Decision tree below.                                  |
| `shimkit adguard verify`                           | Loopback DNS query + `/control/status` probe.                    |
| `shimkit adguard ports show`                       | Read `dns.port` / `http.port` from yaml.                         |
| `shimkit adguard ports set --dns N --http N`       | API-first, yaml fallback with service stop + atomic write.       |
| `shimkit adguard config validate`                  | `AdGuardHome --check-config`.                                    |
| `shimkit adguard service start|stop|restart|status`| `systemctl ... AdGuardHome`.                                     |
| `shimkit adguard logs [-n N] [--follow]`           | `journalctl -u AdGuardHome`.                                     |
| `shimkit adguard rollback`                         | Restore the latest yaml + `/etc/resolv.conf` backups.            |

### Decision tree for `fix`

1. **systemd-resolved active?** Write
   `/etc/systemd/resolved.conf.d/90-shimkit-adguardhome.conf` with
   `DNSStubListener=no` and reload-or-restart. Rewrite `/etc/resolv.conf`
   as a symlink to `/run/systemd/resolve/resolv.conf` (the AGH
   FAQ-recommended path) or as a static file if
   `resolv_conf_mode = "static"`.
2. **NetworkManager active?** Write
   `/etc/NetworkManager/conf.d/90-shimkit-adguardhome.conf` with
   `[main]\ndns=none\n` and `nmcli general reload`. Without this NM
   would clobber `/etc/resolv.conf` on the next link event.
3. **Known-safe DNS daemon holding a port?** Stop + disable (dnsmasq,
   bind9, named, unbound).
4. **pi-hole?** Skip unless `--migrate-from-pihole` is set.
5. **Still blocked on dns/http ports?** Remap via the AGH HTTP control
   API if reachable; otherwise stop AGH, edit yaml via `ruamel.yaml`
   (round-trip safe), start AGH.
6. **Restart AGH**.

Flags: `--dry-run`, `--install PATH` (override AGH location),
`--remap-only` (skip systemd-resolved handling), `--dns-cleanup-only`
(only the DNS-side remediation, no AGH yaml or restart),
`--migrate-from-pihole` (stop pi-hole instead of skipping it).

## Typical flows

### 1. Fresh AGH install on Ubuntu 24.04

```bash
sudo shimkit adguard scan          # see what's holding port 53 (likely systemd-resolved)
sudo shimkit adguard fix --dry-run # preview the plan
sudo shimkit adguard fix           # apply
shimkit adguard verify             # confirm resolution
```

### 2. AGH ports got remapped to 5353/8080; need to inspect

```bash
shimkit adguard ports show
```

### 3. Roll back a botched fix

```bash
sudo shimkit adguard rollback
```

## Configuration

```json
{
  "tools": {
    "adguard": {
      "install_candidates": ["/opt/AdGuardHome", "/var/lib/AdGuardHome"],
      "default_remap_dns_port": 5353,
      "default_remap_http_port": 8080,
      "safe_units_to_stop": ["dnsmasq.service", "bind9.service",
                             "named.service", "unbound.service"],
      "resolv_conf_mode": "symlink",
      "prefer_api_over_yaml": true,
      "api_base_url": "http://127.0.0.1:80"
    }
  }
}
```

Auth for the API (`ports set`, `verify`): set `ADGUARD_USER` and
`ADGUARD_PASS` in the environment. Never as CLI flags.

## Exit codes

| Code | Meaning                                                       |
|-----:|---------------------------------------------------------------|
|    0 | Success.                                                      |
|    1 | Step failed.                                                  |
|   69 | Wrong platform (not Linux), AGH not installed, extras missing.|
|   77 | sudo required.                                                |

## Platform support

| Platform | Supported     |
|----------|---------------|
| Ubuntu 22.04 / 24.04 LTS | ✓ — validated each release |
| Other systemd Linux (Debian 12+, Fedora 40+, Arch, …) | Expected to work; not formally validated. See [`../validation-scope.md`](../validation-scope.md#2-distros-beyond-ubuntu-2204--2404). |
| macOS    | ✗ (exits 69)  |
| WSL2     | ✗ (exits 69; systemd-resolved/NM don't behave like bare Linux) |

## Optional extras

Install with:

```bash
uv tool install 'shimkit[adguard]'    # ruamel.yaml + requests + psutil
# or
pipx inject shimkit ruamel.yaml requests psutil
```

## Troubleshooting

- "AdGuard Home install not found" — pass `--install /your/path` or add
  the directory to `tools.adguard.install_candidates`.
- "NetworkManager keeps overwriting /etc/resolv.conf" — verify the
  drop-in landed:
  `cat /etc/NetworkManager/conf.d/90-shimkit-adguardhome.conf` and
  `nmcli general reload`.
- "Yaml edit fails because AGH overwrote it" — the port stops AGH
  before editing; if you see this, AGH was started by another tool
  while the edit was in flight. Re-run `fix`.

## Origin

This tool is the Python port of `shell-scripts/fix-adguardhome-ports.sh`.
The shell version is removed.
