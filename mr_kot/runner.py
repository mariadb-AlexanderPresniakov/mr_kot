from __future__ import annotations

import inspect
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Dict, Tuple

from .registry import CHECK_REGISTRY, FACT_REGISTRY
from .status import Status

_SEVERITY_ORDER: Dict[Status, int] = {
    Status.ERROR: 3,  # treat as most severe
    Status.FAIL: 2,
    Status.WARN: 1,
    Status.PASS: 0,
    Status.SKIP: 0,  # does not worsen overall
}


@dataclass
class CheckResult:
    id: str
    status: Status
    evidence: Any


class Runner:
    def __init__(self) -> None:
        self._fact_cache: Dict[str, Any] = {}

    def run(self) -> Dict[str, Any]:
        """Run all registered checks with resolved facts and return machine-readable dict."""
        results: list[CheckResult] = []

        for check_id, check_fn in CHECK_REGISTRY.items():
            try:
                kwargs = self._resolve_args(check_fn)
                status, evidence = self._run_check(check_fn, kwargs)
            except Exception as exc:  # do not swallow silently; surface as ERROR
                status, evidence = Status.ERROR, f"exception: {exc.__class__.__name__}: {exc}"
            results.append(CheckResult(id=check_id, status=status, evidence=evidence))

        output = self._build_output(results)
        return output

    def _resolve_fact(self, fact_id: str, stack: list[str] | None = None) -> Any:
        if stack is None:
            stack = []
        if fact_id in self._fact_cache:
            return self._fact_cache[fact_id]
        if fact_id in stack:
            cycle = " -> ".join(stack + [fact_id])
            raise ValueError(f"Cycle detected in facts: {cycle}")
        if fact_id not in FACT_REGISTRY:
            raise KeyError(f"Fact '{fact_id}' is not registered")
        fn = FACT_REGISTRY[fact_id]
        kwargs = self._resolve_args(fn, stack + [fact_id])
        value = fn(**kwargs)
        self._fact_cache[fact_id] = value
        return value

    def _resolve_args(self, fn: Callable[..., Any], stack: list[str] | None = None) -> Dict[str, Any]:
        sig = inspect.signature(fn)
        kwargs: Dict[str, Any] = {}
        for name, param in sig.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue  # ignore *args/**kwargs in dependency resolution
            # parameter names map to fact ids
            kwargs[name] = self._resolve_fact(name, stack)
        return kwargs

    def _run_check(self, fn: Callable[..., Tuple[Status | str, Any]], kwargs: Dict[str, Any]) -> Tuple[Status, Any]:
        result = fn(**kwargs)
        if not (isinstance(result, tuple) and len(result) == 2):
            raise ValueError(f"Check '{fn.__name__}' must return a (status, evidence) tuple")
        status_raw, evidence = result
        # Normalize to Status enum (accept strings for ergonomics)
        if isinstance(status_raw, Status):
            status = status_raw
        elif isinstance(status_raw, str):
            try:
                status = Status[status_raw] if status_raw in Status.__members__ else Status(status_raw)
            except Exception:
                raise ValueError(f"Invalid status '{status_raw}' in check '{fn.__name__}'")
        else:
            raise ValueError(f"Invalid status type '{type(status_raw).__name__}' in check '{fn.__name__}'")
        return status, evidence

    def _build_output(self, results: list[CheckResult]) -> Dict[str, Any]:
        items = [
            {"id": r.id, "status": r.status.value, "evidence": r.evidence} for r in results
        ]
        counts: Counter[str] = Counter(r.status.value for r in results)
        # ensure all keys present
        for k in ["PASS", "FAIL", "WARN", "SKIP", "ERROR"]:
            counts.setdefault(k, 0)

        overall: Status = Status.PASS
        # ERROR/FAIL dominate, then WARN, else PASS (SKIP ignored for severity)
        if counts["ERROR"] > 0 or counts["FAIL"] > 0:
            overall = Status.FAIL
        elif counts["WARN"] > 0:
            overall = Status.WARN
        else:
            overall = Status.PASS

        return {
            "overall": overall.value,
            "counts": dict(counts),
            "items": items,
        }


def run() -> Dict[str, Any]:
    """Convenience function: run all checks and return output dict."""
    return Runner().run()
