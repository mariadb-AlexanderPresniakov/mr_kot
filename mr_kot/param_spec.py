from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass(frozen=True)
class ParamSpec:
    """Metadata for a single @parametrize decorator application.

    - name: parameter name to inject into the check function.
    - values: explicit list of values (mutually exclusive with source).
    - source: name of a fact that yields an iterable of values.
    - fail_fast: when True, if any instance of this check fails (FAIL/ERROR),
      remaining instances of the same check are skipped during execution.
    """

    name: str
    values: Optional[List[Any]] = None
    source: Optional[str] = None
    fail_fast: bool = False

    def __post_init__(self) -> None:
        # basic validation mirroring decorators.parametrize
        if (self.values is None) == (self.source is None):
            raise ValueError("ParamSpec requires exactly one of 'values' or 'source'")
