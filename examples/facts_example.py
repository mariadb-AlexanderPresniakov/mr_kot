from __future__ import annotations

import platform
from typing import Any, Dict

from mr_kot import fact


@fact
def os_release() -> Dict[str, Any]:
    return {
        "id": platform.system().lower(),
        "version": platform.release(),
    }


@fact
def cpu_count() -> int:
    try:
        # Python 3.8+:
        import os

        return os.cpu_count() or 1
    except Exception:  # fallback basic case
        return 1
