from __future__ import annotations

from enum import Enum


class Status(str, Enum):
    """Standard result states for checks and validators."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"
    # Raised when an unexpected exception is caught during check/validator execution
    ERROR = "ERROR"
