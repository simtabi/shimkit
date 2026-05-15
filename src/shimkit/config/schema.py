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


class ToolsConfig(_StrictModel):
    java: JavaConfig
    shell: ShellToolConfig
    dns: DnsConfig = Field(default_factory=DnsConfig)
    adguard: AdGuardConfig = Field(default_factory=AdGuardConfig)
    docker_clean: DockerCleanConfig = Field(default_factory=DockerCleanConfig)
    ports: PortsConfig = Field(default_factory=PortsConfig)
    hosts: HostsConfig = Field(default_factory=HostsConfig)


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
