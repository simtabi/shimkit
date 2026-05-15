"""``shimkit framework laravel`` -- Laravel-specific helpers.

Four commands:

- ``perms`` -- cross-distro storage/bootstrap-cache permission fixer.
- ``env``   -- scaffold a fresh ``.env`` with a generated APP_KEY.
- ``cron-install`` -- wraps ``shimkit cron add`` with the
  Laravel-shaped ``php artisan schedule:run`` invocation.
- ``artisan`` -- host or container passthrough to ``php artisan``.

The original ubuntu ``laravel:file-perms.sh`` + ``laravel:initialize.sh``
were skipped at the v0.5.0 audit as too project-shaped. This tool
re-implements the genuinely useful bits cleanly: cross-distro group
detection, no `--force` of `php artisan storage:link`, an
APP_KEY generator that doesn't need PHP on the host.
"""

from __future__ import annotations

from .manager import LaravelManager

__all__ = ["LaravelManager"]
