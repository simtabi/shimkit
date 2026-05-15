"""LEMP recipe — Linux + Nginx + (MySQL|MariaDB|Postgres) + PHP-FPM.

Three containers per project, all attached to a per-project Docker
bridge network so they can talk by name. The user's cwd (or
``--project-root``) is bind-mounted at ``/srv/app`` inside the
php-fpm and nginx containers. Nothing on the host is touched except
the bind-mount root + the published nginx port.

Naming convention:

- network:    ``shimkit-stack-lemp-<project>-net``
- db:         ``shimkit-stack-lemp-<project>-db``
- php-fpm:    ``shimkit-stack-lemp-<project>-php``
- nginx:      ``shimkit-stack-lemp-<project>-nginx``
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from string import Template

from shimkit.config import get_config
from shimkit.core import DockerEnv, get_logger

from ..db.engines import get as get_engine

_LOG = get_logger("stack.lemp")

SCOPE = "stack"
KIND = "lemp"


@dataclass(frozen=True)
class LempState:
    """One project's three-container state. Each role's state is the
    docker-py status string, or ``"missing"`` when the container
    doesn't exist.
    """

    project: str
    network: str
    db: str
    php: str
    nginx: str
    db_engine: str
    host_port: int

    def all_running(self) -> bool:
        return self.db == "running" and self.php == "running" and self.nginx == "running"


# ── Nginx config rendered into the nginx container ─────────────────────

_NGINX_CONF_TEMPLATE = Template("""\
# managed-by: shimkit (stack lemp)
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    root /srv/app;
    index index.php index.html index.htm;

    server_tokens off;
    charset utf-8;

    add_header X-Frame-Options          "DENY" always;
    add_header X-Content-Type-Options   "nosniff" always;
    add_header Referrer-Policy          "no-referrer-when-downgrade" always;

    location / {
        try_files $$uri $$uri/ /index.php?$$args;
    }

    location ~ \\.php$$ {
        fastcgi_pass               ${PHP_HOST}:9000;
        fastcgi_split_path_info    ^(.+\\.php)(/.+)$$;
        fastcgi_index              index.php;
        fastcgi_param              SCRIPT_FILENAME /srv/app$$fastcgi_script_name;
        include                    fastcgi_params;
    }

    location ~ /\\.(?!well-known) {
        deny all;
    }

    location = /favicon.ico {
        access_log off;
        log_not_found off;
    }
}
""")


def _network_name(project: str) -> str:
    return f"shimkit-{SCOPE}-{KIND}-{project}-net"


def _container_name(project: str, role: str) -> str:
    return f"shimkit-{SCOPE}-{KIND}-{project}-{role}"


def render_nginx_conf(*, php_host: str) -> str:
    """Render the nginx config to bind-mount into the nginx container.

    >>> "shimkit-stack-lemp-myproj-php:9000" in render_nginx_conf(
    ...     php_host="shimkit-stack-lemp-myproj-php")
    True
    """
    return _NGINX_CONF_TEMPLATE.substitute(PHP_HOST=php_host)


def _common_labels(project: str, role: str) -> dict[str, str]:
    return {
        "shimkit.tool": SCOPE,
        "shimkit.stack": KIND,
        "shimkit.project": project,
        "shimkit.role": role,
    }


def _safe_password_env(engine_name: str, password: str) -> dict[str, str]:
    """Build the engine-specific env dict for `password`. We reuse the
    W3 engine drivers' `environment_for_up()` so the var name is
    correct for each DB.
    """
    engine = get_engine(engine_name)
    if engine is None:
        raise ValueError(f"Unknown db engine {engine_name!r}")
    return dict(engine.environment_for_up(password=password))


def _db_container_port(engine_name: str) -> int:
    engine = get_engine(engine_name)
    assert engine is not None
    return engine.container_port


def up(
    env: DockerEnv,
    *,
    project: str,
    db_engine: str,
    host_port: int,
    project_root: Path,
    db_password: str,
    dry_run: bool = False,
) -> dict[str, str]:
    """Bring up a fresh LEMP stack or surface "already up".

    Returns a dict of ``role → action`` (``created`` / ``started`` /
    ``already_running``).
    """
    cfg = get_config().tools.stack.lemp
    db_cfg = get_config().tools.db
    db_engine_cfg = db_cfg.engines.get(db_engine)
    if db_engine_cfg is None:
        raise ValueError(f"Unknown db engine {db_engine!r}")

    network = _network_name(project)
    db_name = _container_name(project, "db")
    php_name = _container_name(project, "php")
    nginx_name = _container_name(project, "nginx")

    actions: dict[str, str] = {}

    if dry_run:
        return {
            "network": "would-create",
            "db": "would-create",
            "php": "would-create",
            "nginx": "would-create",
        }

    env.network_get_or_create(network)

    # ── db ───────────────────────────────────────────────────────
    actions["db"] = _ensure_up(
        env,
        name=db_name,
        image=db_engine_cfg.image,
        environment=_safe_password_env(db_engine, db_password),
        network=network,
        labels=_common_labels(project, "db"),
    )

    # ── php-fpm ──────────────────────────────────────────────────
    actions["php"] = _ensure_up(
        env,
        name=php_name,
        image=cfg.php_fpm_image,
        environment={},
        volumes={
            str(project_root): {"bind": "/srv/app", "mode": "rw"},
        },
        network=network,
        labels=_common_labels(project, "php"),
    )

    # ── nginx ────────────────────────────────────────────────────
    nginx_conf = render_nginx_conf(php_host=php_name)
    conf_path = Path(tempfile.gettempdir()) / f"shimkit-stack-lemp-{project}-default.conf"
    conf_path.write_text(nginx_conf, encoding="utf-8")

    actions["nginx"] = _ensure_up(
        env,
        name=nginx_name,
        image=cfg.nginx_image,
        environment={},
        ports={"80/tcp": ("127.0.0.1", host_port)},
        volumes={
            str(project_root): {"bind": "/srv/app", "mode": "rw"},
            str(conf_path): {"bind": "/etc/nginx/conf.d/default.conf", "mode": "ro"},
        },
        network=network,
        labels=_common_labels(project, "nginx"),
    )

    return actions


def down(env: DockerEnv, *, project: str) -> dict[str, str]:
    """Stop + remove the three containers and the network."""
    actions: dict[str, str] = {}
    for role in ("nginx", "php", "db"):
        name = _container_name(project, role)
        existing = env.find(name)
        if existing is None:
            actions[role] = "missing"
            continue
        env.stop(name)
        env.remove(name, force=True)
        actions[role] = "removed"
    if env.network_remove(_network_name(project)):
        actions["network"] = "removed"
    else:
        actions["network"] = "missing"
    return actions


def status(env: DockerEnv, *, project: str) -> LempState:
    cfg = get_config().tools.stack.lemp
    return LempState(
        project=project,
        network=_network_name(project),
        db=_state_of(env, _container_name(project, "db")),
        php=_state_of(env, _container_name(project, "php")),
        nginx=_state_of(env, _container_name(project, "nginx")),
        db_engine=cfg.default_db,
        host_port=cfg.default_port,
    )


def exec_in_php(
    env: DockerEnv,
    *,
    project: str,
    cmd: list[str],
) -> tuple[int, str, str]:
    """Run ``cmd`` inside the php-fpm container. Returns
    ``(exit_code, stdout, stderr)``.
    """
    outcome = env.exec(_container_name(project, "php"), cmd)
    return outcome.exit_code, outcome.stdout, outcome.stderr


# ─── internals ─────────────────────────────────────────────────────────


def _ensure_up(
    env: DockerEnv,
    *,
    name: str,
    image: str,
    environment: dict[str, str],
    network: str,
    labels: dict[str, str],
    ports: dict[str, tuple[str, int]] | None = None,
    volumes: dict[str, dict[str, str]] | None = None,
) -> str:
    """Idempotent container-up. Returns ``"already_running"`` /
    ``"started"`` / ``"created"``.
    """
    existing = env.find(name)
    if existing is not None:
        state = getattr(existing, "status", None)
        if state == "running":
            return "already_running"
        env.start(name)
        return "started"
    env.run(
        image,
        name=name,
        env=environment,
        ports=ports,
        volumes=volumes,
        network=network,
        labels=labels,
        restart_policy={"Name": "unless-stopped"},
    )
    return "created"


def _state_of(env: DockerEnv, name: str) -> str:
    existing = env.find(name)
    if existing is None:
        return "missing"
    return str(getattr(existing, "status", "unknown") or "unknown")
