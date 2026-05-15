"""MariaDB engine driver."""

from __future__ import annotations

from .base import Engine


class MariaDB(Engine):
    """MariaDB 10.x — image ``mariadb:10.11`` by default.

    The CLI client name is ``mariadb`` in 10.6+; older images shipped
    only ``mysql``. The 10.11 image has both.
    """

    name = "mariadb"
    container_port = 3306

    def environment_for_up(
        self, *, password: str, extras: dict[str, str] | None = None
    ) -> dict[str, str]:
        return {
            "MARIADB_ROOT_PASSWORD": password,
            "MARIADB_ROOT_HOST": "%",
        }

    def data_dir(self) -> str:
        return "/var/lib/mysql"

    def shell_argv(self, *, password: str) -> list[str]:
        return ["mariadb", "-uroot", f"-p{password}"]

    def dump_argv(self, *, password: str) -> list[str]:
        return [
            "mariadb-dump",
            "-uroot",
            f"-p{password}",
            "--all-databases",
            "--single-transaction",
        ]
