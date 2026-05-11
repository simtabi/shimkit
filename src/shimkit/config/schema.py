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
    install_url: str = (
        "https://raw.githubusercontent.com/Homebrew/install/97a0b89e0cfce05ce1806c8f9ebc7b3f1813589e/install.sh"
    )


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


class ToolsConfig(_StrictModel):
    java: JavaConfig
    shell: ShellToolConfig


class PackageManagerEntry(_StrictModel):
    install_cmd: str
    update_cmd: str
    upgrade_cmd: str
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
