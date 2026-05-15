"""phpMyAdmin engine driver.

phpMyAdmin isn't a database — it's a web UI that connects to one.
Requires a backing mysql/mariadb container that's already running.
Uses ``host.docker.internal`` so the container connects through the
shimkit-published port on the host (no shared Docker network setup
needed).
"""

from __future__ import annotations

from .base import Engine


class PhpMyAdmin(Engine):
    """phpMyAdmin — image ``phpmyadmin:5`` by default.

    Knobs accepted in ``extras`` at up time:

    - ``"link_host"``: ``host.docker.internal`` by default (the
      Docker-Desktop bridge gateway, and Linux when ``host-gateway``
      is added to ``--add-host``).
    - ``"link_port"``: the host-side port the backing DB is published
      on (default ``13306`` — the shimkit-prefixed mysql port).
    - ``"db_user"``: defaults to ``"root"``.
    - ``"db_password"``: defaults to the value of ``password``
      (i.e. phpMyAdmin uses the same password as the backing DB).

    The container exposes :80; the host port (default 18080) comes
    from ``tools.db.engines.phpmyadmin.default_port``.
    """

    name = "phpmyadmin"
    container_port = 80

    def environment_for_up(
        self, *, password: str, extras: dict[str, str] | None = None
    ) -> dict[str, str]:
        extras = extras or {}
        host = extras.get("link_host", "host.docker.internal")
        port = extras.get("link_port", "13306")
        user = extras.get("db_user", "root")
        pwd = extras.get("db_password", password)
        return {
            "PMA_HOST": host,
            "PMA_PORT": str(port),
            "PMA_USER": user,
            "PMA_PASSWORD": pwd,
        }

    def volume_mounts(self, *, volume_root: str | None) -> dict[str, dict[str, str]]:
        # phpMyAdmin is stateless — sessions are ephemeral. No volume
        # mount, regardless of what the caller requested.
        return {}

    def data_dir(self) -> str:
        # Unused (no volume). Keep abstract-base happy if anyone asks.
        return "/sessions"

    def supports_shell(self) -> bool:
        return False

    def supports_dump(self) -> bool:
        return False
