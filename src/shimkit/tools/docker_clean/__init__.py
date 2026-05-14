"""Docker resource cleanup — ``shimkit docker-clean``.

Ported from ``python/docker-nucker.sh``. The bash version had three
high-severity bugs that this port fixes:

* ``local x=$(...); if [ $? -eq 0 ]`` at lines 632-643 and 655-657 read
  ``local``'s exit code instead of the command's, so build-cache /
  system-prune success/failure was always reported as success.
* ``((var++))`` under ``set -e`` aborted the verify_docker loop on the
  first iteration.
* ``docker builder prune -af`` only touches the legacy local builder;
  buildx-managed caches (named builders) were missed.
"""

from __future__ import annotations

from .manager import DockerCleanManager
from .models import CleanupPlan, DockerDisk

__all__ = ["CleanupPlan", "DockerCleanManager", "DockerDisk"]
