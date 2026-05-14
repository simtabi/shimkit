# shimkit docker-clean

Interactive Docker resource cleanup for Linux + macOS + WSL. Status,
quick cleanup, custom prune (per resource), full nuke (severe — token
required), daemon restart, scheduling snippet emit.

Ported from `python/docker-nucker.sh`. The shell version had three
high-severity bugs that this port fixes:

- `local x=$(...); if [ $? -eq 0 ]` read `local`'s exit code, not the
  command's, so build-cache and system-prune failures were always
  reported as success.
- `((var++))` under `set -e` aborted `verify_docker` on the first
  iteration, so daemon-health verification ran at most once.
- `docker builder prune -af` missed cache held by named buildx
  builders.

## Commands

| Command                                              | Purpose                                             |
|------------------------------------------------------|-----------------------------------------------------|
| `shimkit docker-clean`                               | Interactive menu.                                   |
| `shimkit docker-clean status`                        | `docker system df --format json` parsed + Desktop.  |
| `shimkit docker-clean quick`                         | Stop containers + remove + prune images/vols/nets.  |
| `shimkit docker-clean nuke --confirm DELETE`         | Remove everything (severe — token required).        |
| `shimkit docker-clean restart`                       | Restart Docker (Desktop CLI or systemd).            |
| `shimkit docker-clean stop-all`                      | Stop running containers.                            |
| `shimkit docker-clean prune-images`                  | `docker image prune -a`.                            |
| `shimkit docker-clean prune-volumes`                 | `docker volume prune` (with confirm).               |
| `shimkit docker-clean prune-networks`                | Custom networks only.                               |
| `shimkit docker-clean prune-builders`                | Iterate `docker buildx ls` and prune each.          |
| `shimkit docker-clean orphans`                       | Dangling images + unused volumes only.              |
| `shimkit docker-clean inspect <kind>`                | `containers|images|volumes|networks|cache`.         |
| `shimkit docker-clean compose-down PATH [--volumes]` | `docker compose down [-v]` for one project.         |
| `shimkit docker-clean schedule [--interval=weekly]`  | Print (not install) a launchd / systemd / cron unit.|

Standard flags: `--dry-run`, `--json`, `--quiet`, `--verbose`,
`--log-file`, `--timeout`.

## Typical flows

### 1. Free disk space without losing data

```bash
shimkit docker-clean status         # see what's reclaimable
shimkit docker-clean orphans        # dangling images + unused volumes
shimkit docker-clean prune-builders # the usual largest reclaim
```

### 2. Tear down a single Compose project

```bash
shimkit docker-clean compose-down ./services/dev-stack.yml --volumes
```

### 3. Wipe everything (CI runner reset)

```bash
shimkit docker-clean nuke --confirm DELETE --json
```

### 4. Schedule weekly cleanup on macOS

```bash
shimkit docker-clean schedule --interval=weekly --out ~/Library/LaunchAgents/com.simtabi.shimkit.docker-clean.weekly.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.simtabi.shimkit.docker-clean.weekly.plist
```

## Configuration

```json
{
  "tools": {
    "docker_clean": {
      "nuke_confirm_token": "DELETE",
      "kubernetes_image_patterns": ["registry.k8s.io", "kube-",
                                    "kubernetes", "desktop-"],
      "daemon_verify_timeout_seconds": 30,
      "default_buildx_prune_all": true
    }
  }
}
```

## Exit codes

| Code | Meaning                                                            |
|-----:|--------------------------------------------------------------------|
|    0 | Success.                                                           |
|    1 | Step failed.                                                       |
|   69 | Docker daemon unreachable, extras missing, or unsupported platform.|
|   77 | Permission denied (not in `docker` group).                         |

## Platform support

| Platform | Supported  |
|----------|------------|
| Linux    | ✓          |
| macOS    | ✓ (Desktop preferred via `docker desktop` CLI) |
| WSL      | ✓ (detected via `WSL_DISTRO_NAME` env) |

## Optional extras

```bash
uv tool install 'shimkit[docker-clean]'    # docker-py SDK
# or
pipx inject shimkit docker
```

## Troubleshooting

- "Docker daemon unreachable" — `docker info` from your shell first.
  On macOS: open Docker Desktop. On Linux: `systemctl status docker`.
- "Permission denied" on Linux — add yourself to the `docker` group
  (`sudo usermod -aG docker $USER`, then log out / in).
- `nuke` says "Pass --confirm DELETE" but you passed `--yes` — `--yes`
  is for `[y/N]` prompts. Severe ops need the literal token too.

## Origin

This tool is the Python port of `python/docker-nucker.sh`. The shell
version is removed.
