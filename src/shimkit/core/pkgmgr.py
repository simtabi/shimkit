"""Cross-platform package manager dispatch.

Detection walks ``config.package_managers.preference_order`` and returns
the first manager whose binary is on PATH and whose ``platforms`` list
includes the current OS.

Two template forms are supported (the schema accepts both):

* **Argv-list (preferred, secure).** ``["apt-get", "install", "-y",
  "${pkg}"]``. Rendered with ``shell=False``; the literal token
  ``"${pkg}"`` is substituted to the package name without any shell
  interpolation. No metacharacter injection is possible.
* **String (legacy).** ``"apt-get install -y ${pkg}"``. Rendered with
  ``shell=True`` via :class:`string.Template`. Kept for backward
  compatibility with existing user configs. Callers MUST whitelist
  ``pkg`` (``ShellUpgrader`` checks ``supported_shells``;
  ``JavaInstaller`` checks ``JavaVersion.all()``).

Existing user configs continue to work. New ``defaults.json`` rows use
the argv-list form.
"""

from __future__ import annotations

import shutil
from string import Template
from typing import Literal

from shimkit.config import get_config

from .command import CommandResult, CommandRunner, sudo_prefix
from .platform import Platform

TemplateKind = Literal["install", "update", "upgrade"]
CmdTemplate = str | list[str]


class PackageManager:
    """Detected host package manager with templated install/update/upgrade commands."""

    def __init__(
        self,
        name: str,
        install_cmd: CmdTemplate,
        update_cmd: CmdTemplate,
        upgrade_cmd: CmdTemplate,
    ) -> None:
        self.name = name
        self._templates: dict[TemplateKind, CmdTemplate] = {
            "install": install_cmd,
            "update": update_cmd,
            "upgrade": upgrade_cmd,
        }

    @classmethod
    def detect(cls, platform: Platform) -> PackageManager | None:
        """Return the first available, platform-compatible PM from the config order."""
        cfg = get_config().package_managers
        for name in cfg.preference_order:
            entry = cfg.definitions.get(name)
            if entry is None:
                continue
            if platform.os_key not in entry.platforms:
                continue
            if shutil.which(name):
                return cls(
                    name=name,
                    install_cmd=entry.install_cmd,
                    update_cmd=entry.update_cmd,
                    upgrade_cmd=entry.upgrade_cmd,
                )
        return None

    def template(self, kind: TemplateKind) -> CmdTemplate:
        """Return the raw template (string or argv list) for inspection."""
        return self._templates[kind]

    def install(self, pkg: str) -> CommandResult:
        return self._run("install", pkg=pkg)

    def upgrade(self, pkg: str) -> CommandResult:
        return self._run("upgrade", pkg=pkg)

    def update(self) -> CommandResult:
        return self._run("update", pkg="")

    def render(self, template: CmdTemplate, *, pkg: str = "") -> str:
        """Render a command template with ``${pkg}`` substituted.

        Returns a human-readable string for display purposes (e.g.
        ``simulate``). Both template forms produce the same display.
        """
        if isinstance(template, list):
            return " ".join(pkg if t == "${pkg}" else t for t in template)
        return Template(template).safe_substitute(pkg=pkg)

    def _run(self, kind: TemplateKind, *, pkg: str) -> CommandResult:
        template = self._templates[kind]
        sudo = sudo_prefix()

        if isinstance(template, list):
            # Argv form: no shell, no interpolation. Each token is either
            # literal or the placeholder, which we replace by `pkg` value.
            argv = [pkg if t == "${pkg}" else t for t in template]
            return CommandRunner.run([*sudo, *argv], capture_output=False)

        # Legacy string-template form. The string is rendered through
        # `string.Template.safe_substitute`, then executed via the shell
        # so users who placed shell features (`|`, `&&`) in their config
        # continue to work. Callers must whitelist `pkg`.
        rendered = Template(template).safe_substitute(pkg=pkg)
        if sudo:
            rendered = " ".join(sudo) + " " + rendered
        return CommandRunner.run(rendered, shell=True, capture_output=False)  # nosec B604
