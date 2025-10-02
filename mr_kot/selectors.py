from __future__ import annotations

import inspect
from typing import Any, Callable, List


def ALL(*names: str) -> Callable[..., bool]:  # noqa: N802
    """Return a predicate that is True if all named facts produce truthy values.

    Runner validates names and resolves these facts during selector evaluation.
    Metadata:
    - _mrkot_predicate_type = "ALL"
    - _mrkot_predicate_facts = list(names)
    """

    def _pred(*values: Any) -> bool:  # values correspond to names in order
        return all(bool(v) for v in values)

    _pred._mrkot_predicate_type = "ALL"  # type: ignore[attr-defined]
    _pred._mrkot_predicate_facts = list(names)  # type: ignore[attr-defined]
    return _pred


def ANY(*names: str) -> Callable[..., bool]:  # noqa: N802
    """Return a predicate that is True iff any named fact produces a truthy value.

    Metadata:
    - _mrkot_predicate_type = "ANY"
    - _mrkot_predicate_facts = list(names)
    """

    def _pred(*values: Any) -> bool:
        return any(bool(v) for v in values)

    _pred._mrkot_predicate_type = "ANY"  # type: ignore[attr-defined]
    _pred._mrkot_predicate_facts = list(names)  # type: ignore[attr-defined]
    return _pred


def NOT(expr: Callable[..., bool]) -> Callable[..., bool]:  # noqa: N802
    """Return a predicate that negates another predicate."""

    def _pred(*values: Any) -> bool:
        return not bool(expr(*values))

    _pred._mrkot_predicate_type = "NOT"  # type: ignore[attr-defined]
    # propagate fact metadata if present
    facts: List[str] = list(getattr(expr, "_mrkot_predicate_facts", []) or [])
    if not facts:
        # derive from wrapped predicate signature (exclude *args/**kwargs)
        sig = inspect.signature(expr)
        for name, param in sig.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            facts.append(name)
    _pred._mrkot_predicate_facts = facts  # type: ignore[attr-defined]
    return _pred
