from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple, Union

from .param_spec import ParamSpec
from .registry import register_check, register_fact, register_fixture
from .selectors import ALL
from .status import Status


def fact(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to register a fact provider function.
    The fact id is the function name.
    """
    return register_fact(func)


def check(
    func: Optional[Callable[..., Tuple[Union[Status, str], Any]]] = None,
    *,
    selector: Optional[Union[Callable[..., bool], str]] = None,
    tags: Optional[List[str]] = None,
):
    """Decorator to register a check function.
    The check id is the function name. Checks must return a tuple ``(status, evidence)``
    where ``status`` is a ``Status`` or a string value of the enum, and ``evidence`` is any value.

    Selectors (optional) control whether a check instance should run:
    - ``selector=None``: run unconditionally after parametrization.
    - ``selector`` as a comma-separated string of fact names (e.g., ``"is_ubuntu, has_systemd"``):
      shorthand equivalent to ``ALL("is_ubuntu", "has_systemd")`` or ``is_ubuntu == True and has_systemd == True``.
    - ``selector`` as a callable predicate: takes facts as parameters and returns a boolean depending on its logic.

    Notes:
    - Only facts are allowed in selectors; fixtures are not allowed.
    - String selector parsing rejects empty tokens (e.g., ``"a,,b"``) with ``ValueError``.
    - Validation of fact existence and production errors is performed during planning by the runner.
    """

    def _decorate(fn: Callable[..., Tuple[Union[Status, str], Any]]):
        # Normalize selector: accept callable or comma-separated string of fact names
        sel_obj: Optional[Callable[..., bool]]
        if selector is None:
            sel_obj = None
        elif isinstance(selector, str):
            tokens = [t.strip() for t in selector.split(",")]
            if any(t == "" for t in tokens):
                raise ValueError("Invalid selector string")
            sel_obj = ALL(*tokens)
        elif callable(selector):
            sel_obj = selector
        else:
            raise ValueError("selector must be callable or string")

        # Attach metadata for planner
        fn._mrkot_selector = sel_obj  # type: ignore[attr-defined]
        fn._mrkot_tags = list(tags or [])  # type: ignore[attr-defined]
        # Parametrization metadata list; each entry is (name, values|None, source|None)
        if not hasattr(fn, "_mrkot_params"):
            fn._mrkot_params = []  # type: ignore[attr-defined]
        return register_check(fn)

    if func is not None:
        return _decorate(func)
    return _decorate


def depends(*names: str):
    """Declare dependencies (facts or fixtures) that must be prepared before running a check.

    Usage:
        @depends("mount_ready", "config_parsed")
        @check
        def my_check(...):
            ...

    - `names` must be strings; may be used multiple times and will be merged/deduplicated.
    - Order does not matter.
    """

    # Validate input types
    for n in names:
        if not isinstance(n, str):
            raise TypeError("depends names must be strings")

    def _decorate(fn: Callable[..., Tuple[Status | str, Any]]):
        existing: list[str] = list(getattr(fn, "_mrkot_depends", []) or [])
        merged = list(dict.fromkeys([*existing, *names]))  # dedupe while preserving first appearance
        fn._mrkot_depends = merged  # type: ignore[attr-defined]
        return fn

    return _decorate


def fixture(func: Callable[..., Any]) -> Callable[..., Any]:
    """Register a fixture provider function by name.
    Supports normal return or generator (yield for teardown) style.
    """
    return register_fixture(func)


def parametrize(
    name: str,
    *,
    values: Optional[List[Any]] = None,
    source: Optional[str] = None,
    fail_fast: bool = False,
):
    """Decorator to parametrize a check function.

    - values: list of concrete values
    - source: name of a fact that yields an iterable of values
    - fail_fast: when True, if any instance of this check fails (FAIL/ERROR), remaining
      instances of the same check are skipped during execution.
    Multiple uses compose via Cartesian product.

    """
    if (values is None) == (source is None):
        raise ValueError("parametrize requires exactly one of 'values' or 'source'")

    def _decorate(fn: Callable[..., Tuple[Status | str, Any]]):
        # Store ParamSpec entries
        params: list[Any] = list(getattr(fn, "_mrkot_params", []) or [])
        params.append(ParamSpec(name=name, values=list(values) if values is not None else None, source=source, fail_fast=fail_fast))
        fn._mrkot_params = params  # type: ignore[attr-defined]
        return fn

    return _decorate
