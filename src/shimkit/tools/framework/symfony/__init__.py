"""``shimkit framework symfony`` -- Symfony-specific helpers.

Four commands:

- ``perms`` -- cross-distro permission fixer for ``var/``.
- ``env``   -- scaffold ``.env.local`` with a generated APP_SECRET.
- ``cache-clear`` -- wraps ``php bin/console cache:clear``.
- ``console`` -- host or container passthrough to ``bin/console``.

Symfony has no built-in scheduler like Laravel's, so there's no
``cron-install`` command. Application-specific cron entries can
be installed via ``shimkit cron add`` directly.
"""

from __future__ import annotations

from .manager import SymfonyManager

__all__ = ["SymfonyManager"]
