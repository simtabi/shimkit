"""SSH key + agent + perms hygiene — ``shimkit ssh``.

Generate / rotate keys, manage ``ssh-agent``, audit + prune
``known_hosts``, audit + fix ``~/.ssh`` permissions, and read your
``~/.ssh/config``. No third-party deps — every operation shells out
to baseline ``ssh-keygen`` / ``ssh-add`` / ``ssh-agent`` /
``ssh-keyscan``.
"""

from __future__ import annotations

from .manager import SshManager
from .models import AgentKey, KeyEntry, PermIssue

__all__ = ["AgentKey", "KeyEntry", "PermIssue", "SshManager"]
