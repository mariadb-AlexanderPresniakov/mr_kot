from __future__ import annotations

from typing import Any, Callable, Tuple

from .registry import register_check, register_fact
from .status import Status


def fact(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to register a fact provider function.
    The fact id is the function name.
    """
    return register_fact(func)


def check(func: Callable[..., Tuple[Status | str, Any]]) -> Callable[..., Tuple[Status | str, Any]]:
    """Decorator to register a check function.
    The check id is the function name. Must return (status, evidence).
    """
    return register_check(func)
