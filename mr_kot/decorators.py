from __future__ import annotations

from typing import Any, Callable, Tuple

from .registry import register_check, register_fact, register_fixture
from .status import Status


def fact(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to register a fact provider function.
    The fact id is the function name.
    """
    return register_fact(func)


def check(
    func: Callable[..., Tuple[Status | str, Any]] | None = None,
    *,
    selector: Callable[..., bool] | None = None,
    tags: list[str] | None = None,
):
    """Decorator to register a check function.
    The check id is the function name. Must return (status, evidence).

    Optional selector is a callable that takes ONLY facts and returns bool.
    """

    def _decorate(fn: Callable[..., Tuple[Status | str, Any]]):
        # Attach metadata for planner
        fn._mrkot_selector = selector  # type: ignore[attr-defined]
        fn._mrkot_tags = list(tags or [])  # type: ignore[attr-defined]
        # Parametrization metadata list; each entry is (name, values|None, source|None)
        if not hasattr(fn, "_mrkot_params"):
            fn._mrkot_params = []  # type: ignore[attr-defined]
        return register_check(fn)

    if func is not None:
        return _decorate(func)
    return _decorate


def fixture(func: Callable[..., Any]) -> Callable[..., Any]:
    """Register a fixture provider function by name.
    Supports normal return or generator (yield for teardown) style.
    """
    return register_fixture(func)


def parametrize(name: str, *, values: list[Any] | None = None, source: str | None = None):
    """Decorator to parametrize a check function.

    - values: list of concrete values
    - source: name of a fact that yields an iterable of values
    Multiple uses compose via Cartesian product.
    """

    if (values is None) == (source is None):
        raise ValueError("parametrize requires exactly one of 'values' or 'source'")

    def _decorate(fn: Callable[..., Tuple[Status | str, Any]]):
        params: list[tuple[str, list[Any] | None, str | None]] = getattr(fn, "_mrkot_params", [])
        params.append((name, values, source))
        fn._mrkot_params = params  # type: ignore[attr-defined]
        return fn

    return _decorate
