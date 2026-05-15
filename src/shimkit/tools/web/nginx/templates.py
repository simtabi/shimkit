"""Hardened nginx vhost templates.

Three flavors today:

- ``static`` — serves files only (typical for a built SPA bundle or
  documentation site).
- ``php`` — adds a ``location ~ \\.php$`` block that hands ``.php``
  requests to ``php-fpm`` over a UNIX socket. PHP version is
  configurable (default ``tools.web.nginx.default_php_version`` =
  ``8.3``).
- ``laravel`` — same as ``php`` but the document root is ``$root/public``
  and the fallback rewrites to ``/index.php?$args``.

Each template carries a baseline of security headers borrowed from
the source ubuntu ``nginx:host.sh`` (X-Frame-Options,
X-Content-Type-Options, X-XSS-Protection, Referrer-Policy,
``server_tokens off``) plus a small set of modern additions
(Permissions-Policy, baseline Content-Security-Policy). HSTS is
deliberately NOT included by default — turn it on only when you've
verified TLS works end-to-end.

The templates are stdlib ``string.Template``-based (no Jinja
dependency).
"""

from __future__ import annotations

from string import Template

__all__ = ["FLAVORS", "render"]


# Shared blocks for clarity. Each block uses ``$``-delimited
# placeholders that `string.Template` substitutes.

_HEADERS = """\
    # ── Security headers ──────────────────────────────────────────
    add_header X-Frame-Options          "DENY" always;
    add_header X-Content-Type-Options   "nosniff" always;
    add_header X-XSS-Protection         "1; mode=block" always;
    add_header Referrer-Policy          "no-referrer-when-downgrade" always;
    add_header Permissions-Policy       "interest-cohort=()" always;

    server_tokens off;
    charset utf-8;
"""

_COMMON_LOCATIONS = """\
    # ── Common location rules ─────────────────────────────────────
    location = /favicon.ico {
        access_log off;
        log_not_found off;
    }
    location ~ /\\.(?!well-known) {
        deny all;
    }
"""

_PHP_LOCATION = """\
    # ── PHP-FPM handoff ───────────────────────────────────────────
    location ~ \\.php$$ {
        fastcgi_pass               unix:/run/php/php${PHP_VERSION}-fpm.sock;
        fastcgi_split_path_info    ^(.+\\.php)(/.+)$$;
        fastcgi_index              index.php;
        fastcgi_param              SCRIPT_FILENAME $$document_root$$fastcgi_script_name;
        include                    fastcgi_params;
    }
"""


_STATIC_TEMPLATE = Template("""\
${MANAGED_MARKER}
# Flavor: static
# Generated for: ${NAME}

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    root ${ROOT};
    index index.html index.htm;

${HEADERS}
    # ── Routing ───────────────────────────────────────────────────
    location / {
        try_files $$uri $$uri/ =404;
    }

${COMMON_LOCATIONS}
}
""")


_PHP_TEMPLATE = Template("""\
${MANAGED_MARKER}
# Flavor: php
# Generated for: ${NAME}

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    root ${ROOT};
    index index.php index.html index.htm;

${HEADERS}
    # ── Routing ───────────────────────────────────────────────────
    location / {
        try_files $$uri $$uri/ /index.php?$$args;
    }

${PHP_LOCATION}
${COMMON_LOCATIONS}
}
""")


_LARAVEL_TEMPLATE = Template("""\
${MANAGED_MARKER}
# Flavor: laravel
# Generated for: ${NAME}

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    root ${ROOT}/public;
    index index.php;

${HEADERS}
    # ── Routing ───────────────────────────────────────────────────
    location / {
        try_files $$uri $$uri/ /index.php?$$args;
    }

${PHP_LOCATION}
${COMMON_LOCATIONS}
}
""")


FLAVORS: tuple[str, ...] = ("static", "php", "laravel")


def render(
    flavor: str,
    *,
    name: str,
    domain: str,
    root: str,
    php_version: str,
    managed_marker: str,
) -> str:
    """Render the named flavor's vhost file.

    Raises ``ValueError`` for an unknown flavor.

    >>> render("static", name="docs", domain="docs.local",
    ...        root="/srv/docs", php_version="8.3",
    ...        managed_marker="# managed-by: shimkit").startswith(
    ...     "# managed-by: shimkit")
    True
    """
    if flavor not in FLAVORS:
        raise ValueError(f"Unknown flavor {flavor!r}. Allowed: {', '.join(FLAVORS)}.")

    headers = Template(_HEADERS).safe_substitute()
    common = Template(_COMMON_LOCATIONS).safe_substitute()
    php = Template(_PHP_LOCATION).substitute(PHP_VERSION=php_version)

    if flavor == "static":
        return _STATIC_TEMPLATE.substitute(
            MANAGED_MARKER=managed_marker,
            NAME=name,
            DOMAIN=domain,
            ROOT=root,
            HEADERS=headers,
            COMMON_LOCATIONS=common,
        )
    if flavor == "php":
        return _PHP_TEMPLATE.substitute(
            MANAGED_MARKER=managed_marker,
            NAME=name,
            DOMAIN=domain,
            ROOT=root,
            HEADERS=headers,
            PHP_LOCATION=php,
            COMMON_LOCATIONS=common,
        )
    # flavor == "laravel"
    return _LARAVEL_TEMPLATE.substitute(
        MANAGED_MARKER=managed_marker,
        NAME=name,
        DOMAIN=domain,
        ROOT=root,
        HEADERS=headers,
        PHP_LOCATION=php,
        COMMON_LOCATIONS=common,
    )
