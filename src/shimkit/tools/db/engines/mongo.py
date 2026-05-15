"""MongoDB engine driver."""

from __future__ import annotations

from .base import Engine


class Mongo(Engine):
    """MongoDB 7.x — image ``mongo:7`` by default. Initialises with a
    root user named ``admin``.
    """

    name = "mongo"
    container_port = 27017

    def environment_for_up(
        self, *, password: str, extras: dict[str, str] | None = None
    ) -> dict[str, str]:
        return {
            "MONGO_INITDB_ROOT_USERNAME": "admin",
            "MONGO_INITDB_ROOT_PASSWORD": password,
        }

    def data_dir(self) -> str:
        return "/data/db"

    def shell_argv(self, *, password: str) -> list[str]:
        # mongosh ships in `mongo:7` by default.
        return [
            "mongosh",
            "--username",
            "admin",
            "--password",
            password,
            "--authenticationDatabase",
            "admin",
        ]

    def dump_argv(self, *, password: str) -> list[str]:
        # `--archive` writes to stdout in mongo's archive format.
        return [
            "mongodump",
            "--username",
            "admin",
            "--password",
            password,
            "--authenticationDatabase",
            "admin",
            "--archive",
            "--quiet",
        ]
