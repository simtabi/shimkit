"""MySQL engine driver."""

from __future__ import annotations

from .base import Engine


class MySQL(Engine):
    """MySQL 8.x — image ``mysql:8.0`` by default."""

    name = "mysql"
    container_port = 3306

    def environment_for_up(
        self, *, password: str, extras: dict[str, str] | None = None
    ) -> dict[str, str]:
        return {
            "MYSQL_ROOT_PASSWORD": password,
            # Strong-but-passable defaults; users can override via the
            # underlying image at their own risk.
            "MYSQL_ROOT_HOST": "%",
        }

    def data_dir(self) -> str:
        return "/var/lib/mysql"

    def shell_argv(self, *, password: str) -> list[str]:
        # `-p<pwd>` (no space) is the documented mysql client form.
        return ["mysql", "-uroot", f"-p{password}"]

    def dump_argv(self, *, password: str) -> list[str]:
        return [
            "mysqldump",
            "-uroot",
            f"-p{password}",
            "--all-databases",
            "--single-transaction",
            "--quick",
        ]

    def supports_on_host(self) -> bool:
        return True

    def host_shell_argv(self, *, password: str) -> list[str]:
        if password:
            return ["mysql", "-h", "127.0.0.1", "-uroot", f"-p{password}"]
        # No password -> let mysql client prompt interactively.
        return ["mysql", "-h", "127.0.0.1", "-uroot", "-p"]
