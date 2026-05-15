"""PostgreSQL engine driver."""

from __future__ import annotations

from .base import Engine


class Postgres(Engine):
    """Postgres 16.x — image ``postgres:16`` by default. Admin user is
    ``postgres``; the env var ``POSTGRES_PASSWORD`` initialises it on
    first run.
    """

    name = "postgres"
    container_port = 5432

    def environment_for_up(
        self, *, password: str, extras: dict[str, str] | None = None
    ) -> dict[str, str]:
        return {
            "POSTGRES_PASSWORD": password,
            "POSTGRES_USER": "postgres",
        }

    def data_dir(self) -> str:
        return "/var/lib/postgresql/data"

    def shell_argv(self, *, password: str) -> list[str]:
        # psql reads PGPASSWORD from env; we pass via `docker exec -e`.
        return ["psql", "-U", "postgres"]

    def dump_argv(self, *, password: str) -> list[str]:
        return ["pg_dumpall", "-U", "postgres", "--clean"]
