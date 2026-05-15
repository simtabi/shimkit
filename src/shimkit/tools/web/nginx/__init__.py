"""``shimkit web nginx`` — nginx vhost generator + opt-in apply.

Default mode is **file-only**: ``shimkit web nginx vhost generate``
writes a hardened vhost to stdout (or a path you specify with
``--out``). Nothing on the host is touched.

``shimkit web nginx vhost apply`` is SEVERE-tier: it copies into
``/etc/nginx/sites-available/``, symlinks into ``sites-enabled/``,
and runs ``nginx -s reload``. It refuses to overwrite a vhost that
isn't tagged with the shimkit managed-marker.
"""

from __future__ import annotations

from .manager import WebNginxManager

__all__ = ["WebNginxManager"]
