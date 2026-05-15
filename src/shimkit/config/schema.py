"""Typed configuration schema.

The single source of truth for what shimkit reads from JSON. Every value
here was previously a class-level constant or a hard-coded literal somewhere
in the legacy script. Externalising them lets users override behaviour
without forking, while pydantic gives us validation and JSON Schema export
for editor autocomplete.

Logic-critical strings (idempotency markers, regex patterns, atomic-replace
semantics) intentionally stay in code — see CONTRIBUTING.md for the rule.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    """Base model that rejects unknown keys, so typos surface loudly."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class UIConfig(_StrictModel):
    color: Literal["auto", "always", "never"] = "auto"
    back_label: str = "← Back"


class SelfUpdateConfig(_StrictModel):
    enabled: bool = True
    check_on_startup: bool = True
    github_repo: str = "simtabi/shimkit"


class BrewConfig(_StrictModel):
    # Pinned to a known-good Homebrew/install commit by default. Bump in
    # defaults.json when needed; users can override via shimkit.json. Do not
    # use HEAD here — that's curl|sh against a moving upstream target.
    install_url: str = "https://raw.githubusercontent.com/Homebrew/install/97a0b89e0cfce05ce1806c8f9ebc7b3f1813589e/install.sh"


class JavaVersionEntry(_StrictModel):
    major: int = Field(..., ge=1, le=99, description="Major Java version, e.g. 21")
    label: str = Field(..., description="Short label shown next to the version")
    brew_formula: str = Field(..., description="Homebrew formula, e.g. openjdk@21")
    lts: bool = False
    recommended: bool = False
    deprecated: bool = False


class JavaScanPaths(_StrictModel):
    macos: list[str] = Field(default_factory=list)
    linux: list[str] = Field(default_factory=list)
    container: list[str] = Field(default_factory=list)


class JavaConfig(_StrictModel):
    default_version: int = 21
    supported_versions: list[JavaVersionEntry]
    scan_paths: JavaScanPaths = Field(default_factory=JavaScanPaths)
    oracle_glob_patterns: list[str] = Field(default_factory=list)
    oracle_safe_roots: list[str] = Field(default_factory=list)


class ShellConfigEntry(_StrictModel):
    rc_file: str = Field(..., description="Primary rc file relative to $HOME")
    fallback_rc: str | None = Field(
        default=None, description="Fallback rc file when primary is absent"
    )


class ShellToolConfig(_StrictModel):
    supported_shells: list[str]
    config_map: dict[str, ShellConfigEntry]


class DnsConfig(_StrictModel):
    """macOS DNS recovery tool — `shimkit dns`."""

    test_domains: list[str] = Field(default_factory=lambda: ["google.com", "cloudflare.com"])
    dns_servers: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "cloudflare": ["1.1.1.1", "1.0.0.1"],
            "google": ["8.8.8.8", "8.8.4.4"],
        }
    )
    step_timeout_seconds: int = Field(default=5, ge=1, le=60)
    nuclear_confirm_token: str = "REGENERATE"
    reset_confirm_token: str = "RESET"
    backup_dir: str = "~/Library/Application Support/shimkit/dns-backups"


class AdGuardTargetPort(_StrictModel):
    """One row in `tools.adguard.target_ports`."""

    port: int = Field(..., ge=1, le=65535)
    proto: Literal["tcp", "udp"]
    role: str = Field(..., description="Human-readable role label, e.g. 'DNS'")


class AdGuardConfig(_StrictModel):
    """AdGuard Home port-conflict fixer — `shimkit adguard`."""

    install_candidates: list[str] = Field(
        default_factory=lambda: [
            "/opt/AdGuardHome",
            "/usr/local/AdGuardHome",
            "/var/lib/AdGuardHome",
            "/etc/AdGuardHome",
        ]
    )
    default_remap_dns_port: int = Field(default=5353, ge=1, le=65535)
    default_remap_http_port: int = Field(default=8080, ge=1, le=65535)
    target_ports: list[AdGuardTargetPort] = Field(
        default_factory=lambda: [
            AdGuardTargetPort(port=53, proto="tcp", role="DNS"),
            AdGuardTargetPort(port=53, proto="udp", role="DNS"),
            AdGuardTargetPort(port=80, proto="tcp", role="WebUI"),
            AdGuardTargetPort(port=443, proto="tcp", role="WebUI-TLS"),
            AdGuardTargetPort(port=3000, proto="tcp", role="Setup"),
        ]
    )
    safe_units_to_stop: list[str] = Field(
        default_factory=lambda: [
            "dnsmasq.service",
            "bind9.service",
            "named.service",
            "unbound.service",
        ]
    )
    pihole_unit: str = "pihole-FTL.service"
    resolv_conf_mode: Literal["symlink", "static"] = "symlink"
    prefer_api_over_yaml: bool = True
    api_base_url: str = "http://127.0.0.1:80"


class DockerCleanConfig(_StrictModel):
    """Docker resource cleanup — `shimkit docker-clean`."""

    nuke_confirm_token: str = "DELETE"
    kubernetes_image_patterns: list[str] = Field(
        default_factory=lambda: [
            "registry.k8s.io",
            "kube-",
            "kubernetes",
            "desktop-",
        ]
    )
    daemon_verify_timeout_seconds: int = Field(default=30, ge=1, le=300)
    default_buildx_prune_all: bool = True


class PortsConfig(_StrictModel):
    """Port owner inspection + killer — `shimkit ports`."""

    default_signal: str = "TERM"
    init_pid_severe_token: str = "KILL-INIT"
    # Killing a PID below this threshold is treated as a system-process
    # operation and prompts the severe-tier token. Linux services live
    # below ~1000; user-launched dev servers are typically >1000.
    system_pid_threshold: int = Field(default=100, ge=1, le=65535)


class SshPermsConfig(_StrictModel):
    """File-mode matrix for `shimkit ssh perms`."""

    dir: str = "700"
    private_key: str = "600"
    public_key: str = "644"
    config: str = "644"
    known_hosts: str = "644"
    authorized_keys: str = "644"


class LogsConfig(_StrictModel):
    """System-log tail/grep — `shimkit logs`."""

    default_lines: int = Field(default=100, ge=1, le=100_000)
    # Cap on lines returned from a single `grep` invocation. Stops
    # an over-broad pattern from saturating the terminal.
    max_grep_lines: int = Field(default=5000, ge=1, le=1_000_000)


class GpgConfig(_StrictModel):
    """GPG key + git-signing hygiene — `shimkit gpg`."""

    default_key_type: str = "ed25519"
    # Expiry passed to `gpg --quick-gen-key`. Accepts gpg's relative
    # form (`1y`, `6m`, `0` for never). Default is 1 year so keys
    # don't accumulate forever.
    default_key_expiry: str = "1y"


class EnvConfig(_StrictModel):
    """`.env` viewer + scaffolder — `shimkit env`."""

    # Regex (alternation) of key-name fragments to treat as secrets.
    # Match is case-insensitive, anchored to substring.
    redact_pattern: str = (
        "password|passwd|pwd|secret|token|api[_-]?key|authorization|key|credential"
    )
    # Names tried when no path is given — read in order; first hit wins.
    default_search_paths: list[str] = Field(
        default_factory=lambda: [".env", ".env.local", ".env.development", ".env.production"]
    )


class SshConfig(_StrictModel):
    """SSH key + agent + perms hygiene — `shimkit ssh`."""

    ssh_dir: str = "~/.ssh"
    default_key_type: str = "ed25519"
    perms: SshPermsConfig = Field(default_factory=SshPermsConfig)


class HostsConfig(_StrictModel):
    """/etc/hosts editor — `shimkit hosts`."""

    hosts_path: str = "/etc/hosts"
    apply_list_severe_token: str = "APPLY-LIST"
    # Cap the size of a single `apply-list` call so a bad URL doesn't
    # explode /etc/hosts. Tunable for power users who DO want huge
    # ad-block lists; default is conservative.
    max_entries_per_apply: int = Field(default=5000, ge=1, le=1_000_000)
    # Marker we insert above shimkit-managed entries so future runs can
    # find and update them without disturbing user-authored lines.
    managed_block_marker: str = "# === shimkit-managed ==="


class LempConfig(_StrictModel):
    """`shimkit stack lemp` — three-container LEMP recipe."""

    nginx_image: str = "nginx:1.27-alpine"
    php_fpm_image: str = "php:8.3-fpm"
    default_port: int = Field(default=18080, ge=1, le=65535)
    # One of `tools.db.engines.<engine>` — picks which DB to spin up.
    default_db: str = "mysql"


class StackConfig(_StrictModel):
    """`shimkit stack *` — multi-container app recipes."""

    default_project: str = "shimkit-dev"
    lemp: LempConfig = Field(default_factory=LempConfig)


class WebNginxConfig(_StrictModel):
    """`shimkit web nginx` — vhost generator + (opt-in) host apply."""

    sites_available_dir: str = "/etc/nginx/sites-available"
    sites_enabled_dir: str = "/etc/nginx/sites-enabled"
    reload_cmd: list[str] = Field(default_factory=lambda: ["nginx", "-s", "reload"])
    apply_severe_token: str = "APPLY-VHOST"
    remove_severe_token: str = "REMOVE-VHOST"
    default_php_version: str = "8.3"
    default_flavor: str = "static"
    # Marker comment inserted at the top of generated vhost files so
    # `vhost list` / `vhost remove` can identify shimkit-managed
    # configs.
    managed_marker: str = "# managed-by: shimkit"


class WebConfig(_StrictModel):
    """Parent for the `shimkit web *` family of tools."""

    nginx: WebNginxConfig = Field(default_factory=WebNginxConfig)


class DbEngineEntry(_StrictModel):
    """Per-engine container settings — image + default port."""

    image: str
    default_port: int = Field(ge=1, le=65535)


class DbConfig(_StrictModel):
    """`shimkit db` — container-first database orchestration."""

    default_volume_root: str = "~/.shimkit/data/db"
    default_bind_host: str = "127.0.0.1"
    default_id: str = "dev"
    # Default password for the engine admin user. Used when --password
    # isn't passed; the random-per-container path uses this as the
    # fallback when secret-generation fails.
    default_password: str = "shimkit-dev"
    reset_severe_token: str = "RESET-DB"
    engines: dict[str, DbEngineEntry] = Field(
        default_factory=lambda: {
            "mysql": DbEngineEntry(image="mysql:8.0", default_port=13306),
            "mariadb": DbEngineEntry(image="mariadb:10.11", default_port=13307),
            "postgres": DbEngineEntry(image="postgres:16", default_port=15432),
            "mongo": DbEngineEntry(image="mongo:7", default_port=17017),
            "phpmyadmin": DbEngineEntry(image="phpmyadmin:5", default_port=18080),
        }
    )


class VersionConstraint(_StrictModel):
    """User-declarable acceptable-range for one external tool.

    `min` / `max` accept either a bare version (interpreted as `>=`
    / `<=`) or an explicit specifier (e.g. ``"<25.0"``). `preferred`
    is informational only.
    """

    min: str | None = None
    max: str | None = None
    preferred: str | None = None


class VersionsConfig(_StrictModel):
    """Per-tool version constraints. Every field optional.

    Adding a new entry requires the detector also being registered in
    :mod:`shimkit.core.version`; an entry without a detector is
    silently ignored.
    """

    docker: VersionConstraint = Field(default_factory=VersionConstraint)
    nginx: VersionConstraint = Field(default_factory=VersionConstraint)
    git: VersionConstraint = Field(default_factory=VersionConstraint)
    gpg: VersionConstraint = Field(default_factory=VersionConstraint)
    python: VersionConstraint = Field(default_factory=VersionConstraint)
    php: VersionConstraint = Field(default_factory=VersionConstraint)
    openssl: VersionConstraint = Field(default_factory=VersionConstraint)


class FrameworkLaravelConfig(_StrictModel):
    """`shimkit framework laravel` — Laravel-specific helpers."""

    # Cross-distro group name. Override if your nginx/php-fpm runs
    # under a different group (apache on RHEL, _www on macOS, ...).
    web_group: str = "www-data"
    # Modes applied by `framework laravel perms`.
    file_mode: str = "664"
    dir_mode: str = "775"
    writable_dirs: list[str] = Field(
        default_factory=lambda: ["storage", "bootstrap/cache"]
    )
    # Default schedule for `cron-install` — Laravel scheduler runs
    # every minute; the application's own kernel decides what to do
    # within that tick.
    default_cron_schedule: str = "* * * * *"


class FrameworkConfig(_StrictModel):
    """Parent for the `shimkit framework *` family of tools."""

    laravel: FrameworkLaravelConfig = Field(default_factory=FrameworkLaravelConfig)


class TlsConfig(_StrictModel):
    """`shimkit tls` — TLS cert lifecycle via container-first certbot."""

    # Volume root for /etc/letsencrypt content. Persists across renewals.
    data_dir: str = "~/.shimkit/data/tls"
    # Certbot image to run one-shot. Pin to a known-good version rather
    # than `:latest` so a registry-side image change can't break renewals
    # silently.
    certbot_image: str = "certbot/certbot:v3.0.1"
    # Default ACME challenge method. Only `webroot` is wired today;
    # `dns-cloudflare` etc. land as opt-in extras in a later release.
    default_method: Literal["webroot"] = "webroot"
    # ACME account email. Required by Let's Encrypt for issuance unless
    # `--register-unsafely-without-email` is passed (we don't expose
    # that flag). User config overrides per-install.
    default_email: str | None = None
    # Default cron schedule for `tls cron-install`. 03:17 daily — well
    # outside business hours and offset from on-the-hour cron herd.
    renewal_schedule: str = "17 3 * * *"
    # SEVERE-tier token for `tls revoke`.
    revoke_severe_token: str = "REVOKE-TLS"


class CronConfig(_StrictModel):
    """`shimkit cron` — generic user-crontab editor."""

    # Comment that identifies a shimkit-managed entry. Format on disk:
    #   # shimkit:<name>
    #   <schedule> <command>
    managed_prefix: str = "# shimkit:"
    backup_dir: str = "~/.shimkit/data/cron"
    # Max entries shimkit will manage per crontab — keeps a malicious
    # config from explosion-installing.
    max_managed_entries: int = Field(default=200, ge=1, le=10_000)


class ToolsConfig(_StrictModel):
    java: JavaConfig
    shell: ShellToolConfig
    dns: DnsConfig = Field(default_factory=DnsConfig)
    adguard: AdGuardConfig = Field(default_factory=AdGuardConfig)
    docker_clean: DockerCleanConfig = Field(default_factory=DockerCleanConfig)
    ports: PortsConfig = Field(default_factory=PortsConfig)
    hosts: HostsConfig = Field(default_factory=HostsConfig)
    ssh: SshConfig = Field(default_factory=SshConfig)
    env: EnvConfig = Field(default_factory=EnvConfig)
    gpg: GpgConfig = Field(default_factory=GpgConfig)
    logs: LogsConfig = Field(default_factory=LogsConfig)
    db: DbConfig = Field(default_factory=DbConfig)
    stack: StackConfig = Field(default_factory=StackConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    cron: CronConfig = Field(default_factory=CronConfig)
    tls: TlsConfig = Field(default_factory=TlsConfig)
    framework: FrameworkConfig = Field(default_factory=FrameworkConfig)
    versions: VersionsConfig = Field(default_factory=VersionsConfig)


class PackageManagerEntry(_StrictModel):
    # Each *_cmd may be either:
    #   - a string template (legacy form; rendered with shell=True). Kept
    #     for backward compatibility with existing user configs.
    #   - a list of argv tokens with literal ``${pkg}`` placeholders
    #     (preferred form; rendered with shell=False, no interpolation).
    # New defaults.json entries use the argv-list form. See
    # PackageManager._run for the dispatch rule.
    install_cmd: str | list[str]
    update_cmd: str | list[str]
    upgrade_cmd: str | list[str]
    platforms: list[Literal["macos", "linux"]]


class PackageManagersConfig(_StrictModel):
    preference_order: list[str]
    definitions: dict[str, PackageManagerEntry]


class ShimkitConfig(_StrictModel):
    """Root configuration model."""

    schema_version: int = Field(
        default=1,
        ge=1,
        description="Bump when defaults.json shape changes; gated by a migration",
    )
    ui: UIConfig = Field(default_factory=UIConfig)
    self_update: SelfUpdateConfig = Field(default_factory=SelfUpdateConfig)
    brew: BrewConfig = Field(default_factory=BrewConfig)
    tools: ToolsConfig
    package_managers: PackageManagersConfig


CURRENT_SCHEMA_VERSION = 1
