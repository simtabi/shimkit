"""Redis engine driver (v0.15.0+).

Redis differs from the SQL engines in two ways:

1. **No env-var password.** The official ``redis:7-alpine`` image
   doesn't read a ``REDIS_PASSWORD`` env var (that's a Bitnami
   convention). To set AUTH we pass ``--requirepass <pw>`` as the
   container command — hence the ``up_command()`` override.

2. **No dump.** Redis's RDB format isn't a stream of SQL — it's a
   binary snapshot tied to a specific server version. The
   "right" backup story is volume-level (the ``/data/dump.rdb``
   file inside our managed volume), not a logical dump piped to
   stdout. We return ``supports_dump=False`` so the manager
   surfaces a clear error rather than emitting half-broken bytes.

3. **No --on-host.** Same reason as mongo / phpmyadmin: shimkit
   doesn't install host packages. Users wanting host Redis run
   ``brew install redis`` or ``apt install redis-server``
   themselves and manage it via systemd / brew services directly.
"""

from __future__ import annotations

from .base import Engine


class Redis(Engine):
    """Redis 7.x — image ``redis:7-alpine`` by default. Port :16379
    on the host; container port 6379.

    AUTH is mandatory in shimkit's setup — every shimkit-managed
    container binds 127.0.0.1 only, but the password also defends
    against same-host process snooping (open ports + auth is the
    Redis-recommended posture).
    """

    name = "redis"
    container_port = 6379

    def environment_for_up(
        self, *, password: str, extras: dict[str, str] | None = None
    ) -> dict[str, str]:
        # Redis ignores env vars; AUTH happens via --requirepass in
        # up_command. We return {} so the manager's standard
        # `docker run -e ...` flow is a no-op.
        return {}

    def up_command(self, *, password: str) -> list[str]:
        # Override the image's default CMD to enable AUTH +
        # AOF persistence (the recommended dev posture).
        return [
            "redis-server",
            "--requirepass",
            password,
            "--appendonly",
            "yes",
        ]

    def data_dir(self) -> str:
        return "/data"

    def shell_argv(self, *, password: str) -> list[str]:
        # `--no-auth-warning` keeps stderr clean when the password
        # is passed via flag (it's a known leak in `ps` output, but
        # inside a shimkit-managed container the surface is the
        # user's own laptop).
        if password:
            return ["redis-cli", "--no-auth-warning", "-a", password]
        return ["redis-cli"]

    def supports_dump(self) -> bool:
        # See module docstring — Redis backups are volume-level, not
        # logical dumps. The user can `shimkit db redis shell` and run
        # `SAVE` / `BGSAVE` to trigger an RDB write to /data/dump.rdb.
        return False
