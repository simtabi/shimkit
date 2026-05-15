"""GPG key + git-signing hygiene — ``shimkit gpg``.

Generates / lists / exports GPG keys, manages ``gpg-agent`` state,
and writes the right ``user.signingkey`` + ``commit.gpgsign`` config
for git commit signing. No third-party deps; shells out to ``gpg``
and ``git`` via :class:`shimkit.core.CommandRunner`.

Passphrases are read by ``gpg`` directly from the TTY — shimkit
never sees, captures, or logs them.
"""

from __future__ import annotations

from .manager import GpgManager
from .models import GpgKey

__all__ = ["GpgKey", "GpgManager"]
