"""Per-engine drivers for ``shimkit db``.

Each engine is a small class implementing :class:`Engine` that
declares its image, default port, environment for `up`, and the
argv vectors for `shell` / `dump` inside the running container.

Registry lives in this module — adding a new engine is one new file
plus a single dictionary entry.
"""

from __future__ import annotations

from .base import Engine, UnsupportedEngineOperationError
from .mariadb import MariaDB
from .mongo import Mongo
from .mysql import MySQL
from .phpmyadmin import PhpMyAdmin
from .postgres import Postgres
from .redis import Redis

# Insertion order is preserved so `db ls` / help output is stable.
REGISTRY: dict[str, Engine] = {
    "mysql": MySQL(),
    "mariadb": MariaDB(),
    "postgres": Postgres(),
    "mongo": Mongo(),
    "redis": Redis(),
    "phpmyadmin": PhpMyAdmin(),
}


def get(name: str) -> Engine | None:
    """Return the engine instance for ``name`` (case-sensitive), or
    ``None`` when not in the registry.
    """
    return REGISTRY.get(name)


__all__ = [
    "REGISTRY",
    "Engine",
    "MariaDB",
    "Mongo",
    "MySQL",
    "PhpMyAdmin",
    "Postgres",
    "Redis",
    "UnsupportedEngineOperationError",
    "get",
]
