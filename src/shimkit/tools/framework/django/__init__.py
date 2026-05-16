"""``shimkit framework django`` -- Django-specific helpers (v0.16.0+).

Four commands:

- ``perms`` -- fix ``media/`` + ``staticfiles/`` permissions.
- ``env``   -- scaffold a starter ``.env`` with a generated
  ``SECRET_KEY`` + ``DATABASE_URL`` pointing at the shimkit
  dev DB.
- ``migrate`` -- wraps ``python manage.py migrate``.
- ``manage`` -- generic passthrough to ``python manage.py``.

Django has no built-in scheduler, so there's no ``cron-install``
command. Application-specific cron entries go via ``shimkit cron
add`` directly. The same applies to Symfony (v0.14.0).
"""

from __future__ import annotations

from .manager import DjangoManager

__all__ = ["DjangoManager"]
