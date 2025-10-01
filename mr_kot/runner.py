from __future__ import annotations

import inspect
import logging
import sys
import types
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

from .registry import CHECK_REGISTRY, FACT_REGISTRY, FIXTURE_REGISTRY
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
    tags: List[str]


_LOGGER_NAME = "mr_kot"


class Runner:
    def __init__(self, allowed_tags: set[str] | None = None, include_tags: bool = False, verbose: bool = False) -> None:
        self._fact_cache: Dict[str, Any] = {}
        self._allowed_tags: set[str] | None = set(allowed_tags) if allowed_tags else None
        self._include_tags: bool = include_tags
        self._init_logger(verbose)

    def run(self) -> Dict[str, Any]:
        """Run all registered checks with resolved facts and return machine-readable dict."""
        results: list[CheckResult] = []

        self._log_registry_summary()

        # Iterate checks
        for check_id, check_fn in CHECK_REGISTRY.items():
            include, tags = self._filter_by_tags(check_fn)
            if not include:
                continue
            results.extend(self._run_check_plan(check_id, check_fn, tags))

        return self._build_output(results)

    # ----- Private helpers -----
    def _init_logger(self, verbose: bool) -> None:
        """Initialize the runner logger.

        Logs are emitted to stderr. INFO by default, DEBUG when verbose=True.
        """
        logger = logging.getLogger(_LOGGER_NAME)
        if not logger.handlers:
            handler = logging.StreamHandler(stream=sys.stderr)
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
            logger.propagate = False
        logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        self._logger = logger

    def _log_registry_summary(self) -> None:
        """Log counts and names (DEBUG) for discovered registry items."""
        facts_list = list(FACT_REGISTRY.keys())
        fixtures_list = list(FIXTURE_REGISTRY.keys())
        checks_list = list(CHECK_REGISTRY.keys())
        self._logger.info(
            "[registry] discovered %d facts, %d fixtures, %d checks",
            len(facts_list), len(fixtures_list), len(checks_list),
        )
        if facts_list:
            self._logger.debug("[registry] facts: %s", ", ".join(facts_list))
        if fixtures_list:
            self._logger.debug("[registry] fixtures: %s", ", ".join(fixtures_list))
        if checks_list:
            self._logger.debug("[registry] checks: %s", ", ".join(checks_list))

    def _filter_by_tags(self, check_fn: Callable[..., Any]) -> Tuple[bool, List[str]]:
        """Return (include, tags) for current tag filter configuration."""
        check_tags: List[str] = list(getattr(check_fn, "_mrkot_tags", []) or [])
        if self._allowed_tags is None:
            return True, check_tags
        if not check_tags or self._allowed_tags.isdisjoint(check_tags):
            return False, check_tags
        return True, check_tags

    def _run_check_plan(self, check_id: str, check_fn: Callable[..., Any], check_tags: List[str]) -> List[CheckResult]:
        """Evaluate selector, plan instances, and execute; protect with error surface as ERROR item."""
        out: list[CheckResult] = []
        try:
            # Selector
            sel_ok, sel_result = self._evaluate_selector(check_id, check_fn, check_tags)
            if not sel_ok:
                if sel_result is not None:
                    out.append(sel_result)
                return out

            # Plan instances
            instances = self._plan_instances(check_id, check_fn)
            if not instances:
                return out

            # Execute instances
            out.extend(self._execute_instances(check_fn, instances, check_tags))
            return out
        except Exception as exc:
            out.append(
                CheckResult(id=check_id, status=Status.ERROR, evidence=f"exception: {exc.__class__.__name__}: {exc}", tags=check_tags)
            )
            return out

    # ----- High-level steps -----
    def _evaluate_selector(self, check_id: str, check_fn: Callable[..., Any], tags: List[str]) -> Tuple[bool, CheckResult | None]:
        sel = getattr(check_fn, "_mrkot_selector", None)
        if sel is None:
            return True, None
        # Enforce selector only uses facts
        sel_sig = inspect.signature(sel)
        for name in sel_sig.parameters:
            if name not in FACT_REGISTRY:
                raise ValueError(f"Selector for '{check_id}' must depend only on facts; got '{name}'")
        sel_kwargs = self._resolve_args(sel)
        sel_ok = bool(sel(**sel_kwargs))
        if sel_ok:
            self._logger.info("[selector] check=%s selector satisfied", check_id)
            self._logger.debug("[selector] inputs for %s: %r", check_id, sel_kwargs)
        else:
            self._logger.info("[selector] check=%s selector not satisfied", check_id)
            self._logger.debug("[selector] inputs for %s: %r", check_id, sel_kwargs)
            return False, CheckResult(id=check_id, status=Status.SKIP, evidence="selector=false", tags=tags)
        return True, None

    def _plan_instances(self, check_id: str, check_fn: Callable[..., Any]) -> List[Tuple[str, Dict[str, Any]]]:
        instances = self._expand_params(check_id, check_fn)
        if instances:
            ids = ", ".join(inst_id for inst_id, _ in instances)
            self._logger.debug("[param] expanded %s -> %s", check_id, ids)
        return instances

    def _execute_instances(
        self, check_fn: Callable[..., Tuple[Status | str, Any]], instances: List[Tuple[str, Dict[str, Any]]], tags: List[str]
    ) -> List[CheckResult]:
        out: list[CheckResult] = []
        for inst_id, param_bindings in instances:
            try:
                status, evidence = self._run_check_instance(check_fn, param_bindings)
            except Exception as exc:
                status, evidence = Status.ERROR, f"exception: {exc.__class__.__name__}: {exc}"
            self._logger.info("[check] run id=%s status=%s evidence=%r", inst_id, status.value, evidence)
            out.append(CheckResult(id=inst_id, status=status, evidence=evidence, tags=tags))
        return out

    def _resolve_fact(self, fact_id: str, stack: list[str] | None = None) -> Any:
        if stack is None:
            stack = []
        if fact_id in self._fact_cache:
            return self._fact_cache[fact_id]
        if fact_id in stack:
            cycle = " -> ".join([*stack, fact_id])
            raise ValueError(f"Cycle detected in facts: {cycle}")
        if fact_id not in FACT_REGISTRY:
            raise KeyError(f"Fact '{fact_id}' is not registered")
        fn = FACT_REGISTRY[fact_id]
        kwargs = self._resolve_args(fn, [*stack, fact_id])
        value = fn(**kwargs)
        self._fact_cache[fact_id] = value
        short = repr(value)
        if len(short) > 200:
            short = short[:200] + "..."
        self._logger.debug("[fact] resolved %s=%s", fact_id, short)
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
        if isinstance(status_raw, Status):
            status = status_raw
        elif isinstance(status_raw, str):
            try:
                status = Status[status_raw] if status_raw in Status.__members__ else Status(status_raw)
            except Exception as exc:
                raise ValueError(f"Invalid status '{status_raw}' in check '{fn.__name__}'") from exc
        else:
            raise ValueError(f"Invalid status type '{type(status_raw).__name__}' in check '{fn.__name__}'")
        return status, evidence

    def _build_output(self, results: list[CheckResult]) -> Dict[str, Any]:
        items: list[Dict[str, Any]] = []
        for r in results:
            item = {"id": r.id, "status": r.status.value, "evidence": r.evidence}
            if self._include_tags:
                item["tags"] = r.tags
            items.append(item)
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

        summary = {
            "overall": overall.value,
            "counts": dict(counts),
            "items": items,
        }
        # INFO summary
        self._logger.info(
            "[summary] PASS=%d FAIL=%d WARN=%d SKIP=%d ERROR=%d overall=%s",
            summary["counts"]["PASS"],
            summary["counts"]["FAIL"],
            summary["counts"]["WARN"],
            summary["counts"]["SKIP"],
            summary["counts"]["ERROR"],
            summary["overall"],
        )
        return summary

    # ----- Planner helpers -----
    def _expand_params(self, base_id: str, check_fn: Callable[..., Any]) -> list[tuple[str, Dict[str, Any]]]:
        """Return list of (instance_id, param_bindings) for a check function.
        If no parametrization metadata, returns one instance with empty bindings.
        """
        params: list[tuple[str, list[Any] | None, str | None]] = getattr(check_fn, "_mrkot_params", [])
        if not params:
            return [(base_id, {})]

        # Build list of value lists for each param
        valued: list[tuple[str, list[Any]]] = []
        # Reverse to reflect source decorator order (top-to-bottom), since decorators apply bottom-up
        for name, values, source in reversed(params):
            # source from fact if values is None
            seq = list(values) if values is not None else list(self._resolve_fact(source or ""))
            if not seq:
                return []  # empty -> no instances
            valued.append((name, seq))

        # Cartesian product
        combos: list[Dict[str, Any]] = [{}]
        for name, seq in valued:
            new: list[Dict[str, Any]] = []
            for base in combos:
                for v in seq:
                    b = dict(base)
                    b[name] = v
                    new.append(b)
            combos = new

        # Build instance IDs in top-to-bottom decorator order
        param_names_order: list[str] = [name for name, _seq in valued]
        instances: list[tuple[str, Dict[str, Any]]] = []
        for binding in combos:
            suffix = ",".join(f"{n}={binding[n]!r}" for n in param_names_order)
            inst_id = f"{base_id}[{suffix}]"
            instances.append((inst_id, binding))
        return instances

    def _run_check_instance(self, fn: Callable[..., Tuple[Status | str, Any]], params: Dict[str, Any]) -> Tuple[Status, Any]:
        """Resolve facts and fixtures, merge with params, run fn, and teardown fixtures."""
        sig = inspect.signature(fn)
        kwargs: Dict[str, Any] = {}
        fixture_cache: Dict[str, Any] = {}
        teardowns: list[Callable[[], None]] = []

        def build_fixture(name: str, fstack: list[str] | None = None) -> Any:
            if fstack is None:
                fstack = []
            if name in fixture_cache:
                return fixture_cache[name]
            if name in fstack:
                cycle = " -> ".join([*fstack, name])
                raise ValueError(f"Cycle detected in fixtures: {cycle}")
            if name not in FIXTURE_REGISTRY:
                raise KeyError(f"Fixture '{name}' is not registered")
            ffn = FIXTURE_REGISTRY[name]
            # Resolve deps for fixture: facts and other fixtures
            fkwargs: Dict[str, Any] = {}
            f_sig = inspect.signature(ffn)
            for dep in f_sig.parameters:
                if dep in FIXTURE_REGISTRY:
                    fkwargs[dep] = build_fixture(dep, [*fstack, name])
                else:
                    fkwargs[dep] = self._resolve_fact(dep)
            result = ffn(**fkwargs)
            if isinstance(result, types.GeneratorType):
                gen = result
                value = next(gen)
                def _td(gen: types.GeneratorType = gen) -> None:  # default bind
                    with suppress(StopIteration):
                        next(gen)
                teardowns.append(_td)
            else:
                value = result
            fixture_cache[name] = value
            # DEBUG logs for fixtures
            self._logger.debug("[fixture] built %s=%r", name, value)
            return value

        # Build kwargs
        for name in sig.parameters:
            if name in params:
                kwargs[name] = params[name]
            elif name in FIXTURE_REGISTRY:
                kwargs[name] = build_fixture(name)
            else:
                kwargs[name] = self._resolve_fact(name)

        try:
            return self._run_check(fn, kwargs)
        finally:
            # Teardown in LIFO
            for td in reversed(teardowns):
                with suppress(Exception):
                    td()
                self._logger.debug("[fixture] teardown executed")


def run() -> Dict[str, Any]:
    """Convenience function: run all checks and return output dict."""
    return Runner().run()
