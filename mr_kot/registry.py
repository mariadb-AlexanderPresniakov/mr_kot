from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from .status import Status

# Public registries used by decorators and runner
FACT_REGISTRY: Dict[str, Callable[..., Any]] = {}

CHECK_REGISTRY: Dict[str, Callable[..., Tuple[Status | str, Any]]] = {}

# Fixtures registry
FIXTURE_REGISTRY: Dict[str, Callable[..., Any]] = {}


def register_fact(func: Callable[..., Any]) -> Callable[..., Any]:
    """Register a fact provider function by its function name as ID."""
    existing = FACT_REGISTRY.get(func.__name__)
    if existing is not None and existing is not func:
        raise ValueError(
            "Duplicate fact id '" + func.__name__ + "' between "
            + f"{existing.__module__}.{getattr(existing, '__qualname__', existing.__name__)} and "
            + f"{func.__module__}.{getattr(func, '__qualname__', func.__name__)}"
        )
    FACT_REGISTRY[func.__name__] = func
    return func


def register_check(func: Callable[..., Tuple[Status | str, Any]]) -> Callable[..., Tuple[Status | str, Any]]:
    """Register a check function by its function name as ID."""
    existing = CHECK_REGISTRY.get(func.__name__)
    if existing is not None and existing is not func:
        raise ValueError(
            "Duplicate check id '" + func.__name__ + "' between "
            + f"{existing.__module__}.{getattr(existing, '__qualname__', existing.__name__)} and "
            + f"{func.__module__}.{getattr(func, '__qualname__', func.__name__)}"
        )
    CHECK_REGISTRY[func.__name__] = func
    return func


def register_fixture(func: Callable[..., Any]) -> Callable[..., Any]:
    """Register a fixture provider function by its function name as ID."""
    existing = FIXTURE_REGISTRY.get(func.__name__)
    if existing is not None and existing is not func:
        raise ValueError(
            "Duplicate fixture id '" + func.__name__ + "' between "
            + f"{existing.__module__}.{getattr(existing, '__qualname__', existing.__name__)} and "
            + f"{func.__module__}.{getattr(func, '__qualname__', func.__name__)}"
        )
    FIXTURE_REGISTRY[func.__name__] = func
    return func


def list_facts() -> List[Tuple[str, Callable[..., Any]]]:
    return sorted(FACT_REGISTRY.items(), key=lambda kv: kv[0])


def list_checks() -> List[Tuple[str, Callable[..., Tuple[Status | str, Any]]]]:
    return sorted(CHECK_REGISTRY.items(), key=lambda kv: kv[0])


def list_fixtures() -> List[Tuple[str, Callable[..., Any]]]:
    return sorted(FIXTURE_REGISTRY.items(), key=lambda kv: kv[0])
