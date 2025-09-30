from __future__ import annotations

from examples.facts_example import os_release as _os_release  # noqa: F401 - imported for registration via decorator
from mr_kot import Status, check


@check
def os_is_ubuntu(os_release):
    os_id = os_release.get("id")
    if os_id == "linux":  # simplistic; real-world would parse /etc/os-release
        return (Status.WARN, f"os looks like linux: id={os_id}")
    if os_id in {"darwin", "windows"}:  # non-linux hosts: not applicable
        return (Status.SKIP, f"check targets ubuntu; current os={os_id}")
    if os_id == "ubuntu":
        return (Status.PASS, f"os={os_id}")
    return (Status.WARN, f"not ubuntu: os={os_id}")
