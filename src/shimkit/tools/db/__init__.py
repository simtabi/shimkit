"""``shimkit db`` — container-first database orchestration.

Five engines via a registry pattern: mysql, mariadb, postgres,
mongo, phpmyadmin. Each engine is a small driver under
:mod:`shimkit.tools.db.engines`; the shared manager
(:class:`DbManager`) handles the docker-side lifecycle uniformly
across engines.
"""

from __future__ import annotations

from .engines import REGISTRY, Engine
from .manager import DbManager

__all__ = ["REGISTRY", "DbManager", "Engine"]
