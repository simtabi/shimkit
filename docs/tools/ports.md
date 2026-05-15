# shimkit ports

Cross-platform inspector + killer for the process holding a TCP or
UDP port. Built for the day-to-day case of "port 5000 is in use" when
you don't know what's holding it, or you do and you want it gone.

macOS reads `lsof -nP -iTCP -sTCP:LISTEN -iUDP -F pcnuP`. Linux
reads `ss -tulnpH`. Both outputs are normalised to a single
`PortOwner` dataclass via the pure parsers in
`src/shimkit/tools/ports/owners.py` (unit-testable without
shelling out).

## Commands

| Command                                  | Purpose                                                              |
|------------------------------------------|----------------------------------------------------------------------|
| `shimkit ports`                          | Interactive menu (list-only — kill is subcommand-only).              |
| `shimkit ports show`                     | List every listening socket and the process holding it.              |
| `shimkit ports show <port>`              | Same, narrowed to one port.                                          |
| `shimkit ports kill <port>`              | Signal the holder(s). MODERATE prompt by default.                    |

Every command accepts the standard shared flags: `--quiet`,
`--verbose`, `--log-file`, `--no-color`, `--color`, `--no-input`
(place these before the subcommand). Per-command flags
(`--json`, `--dry-run`, `--yes`, `--force`, `--confirm`,
`--signal`) go after.

## Killing a port

```bash
shimkit ports kill 5000              # interactive MODERATE prompt
shimkit ports kill 5000 --yes        # skip the prompt
shimkit ports kill 5000 --signal KILL --yes
shimkit ports kill 5000 --dry-run    # show targets without signalling
```

Allowed signals: `TERM` (default), `KILL`, `INT`, `HUP`. Anything
else is refused with exit 1 — this CLI is for stopping stuck dev
servers, not for arbitrary IPC.

## Severe tier — system processes

Killing a process with a low PID (below
`tools.ports.system_pid_threshold`, default `100`) requires the
severe-tier token:

```bash
shimkit ports kill 53 --yes --confirm KILL-INIT
```

The default threshold catches systemd-side services on Linux
(systemd-resolved, systemd-networkd, etc.) and the early-boot helpers
on macOS. Bumping the threshold lower in `~/.config/shimkit/shimkit.json`
trades safety for convenience.

Killing pid 1 specifically is refused at any token — `init` is never
the right answer.

## JSON output

```bash
$ shimkit ports show --json
{
  "ts": "...",
  "tool": "ports",
  "step": "show",
  "status": "ok",
  "data": {
    "port": null,
    "owners": [
      {"port": 80, "proto": "tcp", "pid": 1234,
       "name": "nginx", "user": "nobody", "address": null}
    ]
  }
}
```

`port` is `null` when the call was unfiltered. `address` is
`null` for wildcard binds (`0.0.0.0`, `*`, `::`).

## Configuration

```json
{
  "tools": {
    "ports": {
      "default_signal": "TERM",
      "init_pid_severe_token": "KILL-INIT",
      "system_pid_threshold": 100
    }
  }
}
```

## Exit codes

| Code | Meaning                                              |
|-----:|------------------------------------------------------|
| 0    | success / no-op (port empty / nothing to do)         |
| 1    | generic failure (disallowed signal, refused tier, prompt cancelled) |
| 2    | Typer usage error                                    |
| 69   | EX_UNAVAILABLE — wrong platform or `lsof`/`ss` missing |
| 130  | SIGINT                                               |

## Platform support

| Platform | Status |
|----------|--------|
| macOS    | ✓ via `lsof` (preinstalled on every supported macOS).               |
| Linux    | ✓ via `ss` from `iproute2` (preinstalled on most distros).          |
| WSL      | ✓ (Linux path).                                                     |
| Windows  | ✗ — out of charter.                                                 |
