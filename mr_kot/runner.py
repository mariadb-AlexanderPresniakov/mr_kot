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

# Predicate-only selectors; helpers live in selectors.py but are simple callables
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

        # Preflight: validate and produce selector/param-source facts; fail-fast on errors
        self._preflight_selector_and_param_facts()

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
        # Reinitialize handler to bind to current sys.stderr for test capture
        for h in list(logger.handlers):
            logger.removeHandler(h)
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

    # ----- Fail-fast planning -----
    class PlanningError(Exception):
        pass

    def _preflight_selector_and_param_facts(self) -> None:
        """Fail-fast validation and production of facts used by selectors and param sources.

        - Unknown fact names cause a PlanningError
        - Production failures cause a PlanningError
        - Fixtures are not allowed in selectors
        """
        self._logger.info("[selector] preflight: checking facts for selectors and parametrization sources…")

        # Collect selector fact names (predicate params or helper-declared facts)
        selector_fact_names: set[str] = set()
        for check_fn in CHECK_REGISTRY.values():
            sel = getattr(check_fn, "_mrkot_selector", None)
            if sel is None:
                continue
            if not callable(sel):
                raise Runner.PlanningError(f"selector must be a callable or None, got: {type(sel).__name__}")
            # Helper-provided metadata wins; else use signature param names
            helper_facts = list(getattr(sel, "_mrkot_predicate_facts", []) or [])
            if helper_facts:
                for n in helper_facts:
                    if n in FIXTURE_REGISTRY:
                        raise Runner.PlanningError(f"fixtures cannot be used in selectors (facts-only): {n}")
                    if n not in FACT_REGISTRY:
                        raise Runner.PlanningError(f"unknown fact in selector: {n}")
                    selector_fact_names.add(n)
            else:
                sel_sig = inspect.signature(sel)
                for name, param in sel_sig.parameters.items():
                    if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                        continue
                    if name in FIXTURE_REGISTRY:
                        raise Runner.PlanningError(f"fixtures cannot be used in selectors (facts-only): {name}")
                    if name not in FACT_REGISTRY:
                        raise Runner.PlanningError(f"unknown fact in selector: {name}")
                    selector_fact_names.add(name)

        # Do not produce selector facts here; some require instance bindings.
        # Validation above ensures names exist and fixtures are not used.

        # Param sources facts fail-fast
        for check_fn in CHECK_REGISTRY.values():
            params = list(getattr(check_fn, "_mrkot_params", []) or [])
            for _name, _values, source in params:
                if source:
                    if source not in FACT_REGISTRY:
                        raise Runner.PlanningError(f"unknown fact in param source: {source}")
                    try:
                        _ = self._resolve_fact(source)
                    except Exception as exc:
                        raise Runner.PlanningError(f"param source fact failed: {source}: {exc}") from exc

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
            # Plan instances first
            instances = self._plan_instances(check_id, check_fn)
            if not instances:
                return out

            # Filter per-instance by selector
            sel = getattr(check_fn, "_mrkot_selector", None)
            # Each runnable instance may carry per-fact overrides for fact arguments
            runnable: list[Tuple[str, Dict[str, Any], Dict[str, Dict[str, Any]]]] = []
            if sel is None:
                runnable = [(iid, p, {}) for iid, p in instances]
            else:
                for inst_id, params in instances:
                    try:
                        ok, evidence, overrides = self._selector_allows_instance(check_id, sel, params)
                        if ok:
                            self._logger.info("[selector] check=%s satisfied for %s", check_id, inst_id)
                            runnable.append((inst_id, params, overrides))
                        else:
                            # Emit SKIP for this instance
                            self._logger.info("[selector] check=%s not satisfied for %s: %s", check_id, inst_id, evidence)
                            out.append(CheckResult(id=inst_id, status=Status.SKIP, evidence=evidence, tags=check_tags))
                    except Exception as exc:
                        if isinstance(exc, Runner.PlanningError):
                            raise
                        # Non-planning errors in predicate evaluation -> mark instance ERROR
                        out.append(
                            CheckResult(
                                id=inst_id,
                                status=Status.ERROR,
                                evidence=f"exception: {exc.__class__.__name__}: {exc}",
                                tags=check_tags,
                            )
                        )

            if not runnable:
                return out

            # Execute filtered instances
            out.extend(self._execute_instances(check_fn, runnable, check_tags))
            return out
        except Exception as exc:
            if isinstance(exc, Runner.PlanningError):
                raise
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

    def _selector_allows_instance(self, check_id: str, selector: Any, params: Dict[str, Any]) -> Tuple[bool, str | None, Dict[str, Dict[str, Any]]]:
        """Predicate-only evaluation for a single planned instance.

        - Resolve only the facts referenced by the predicate (helper metadata or signature).
        - Bind fact parameters from current instance params by name intersection.
        - On unknown/failing fact during predicate evaluation, raise PlanningError.
        - Return (False, "selector=false", {}) when predicate is falsy (so instance is SKIP).
        """
        sel = selector  # type: ignore[assignment]
        if not callable(sel):
            raise Runner.PlanningError(f"selector must be a callable or None, got: {type(sel).__name__}")

        helper_names = list(getattr(sel, "_mrkot_predicate_facts", []) or [])
        if helper_names:
            values: list[Any] = []
            for fact_name in helper_names:
                if fact_name not in FACT_REGISTRY:
                    raise Runner.PlanningError(f"unknown fact in selector: {fact_name}")
                try:
                    fact_fn = FACT_REGISTRY[fact_name]
                    fsig = inspect.signature(fact_fn)
                    overrides: Dict[str, Any] = {p: params[p] for p in fsig.parameters if p in params}
                    val = self._resolve_fact_with_overrides(fact_name, overrides) if overrides else self._resolve_fact(fact_name)
                    values.append(val)
                except Exception as exc:
                    raise Runner.PlanningError(f"fact {fact_name} failed during selector evaluation: {exc}") from exc
            decision = bool(sel(*values))
            # DEBUG: log inputs and decision
            shorts = []
            for n, v in zip(helper_names, values):
                s = repr(v)
                if len(s) > 200:
                    s = s[:200] + "..."
                shorts.append(f"{n}={s}")
            self._logger.debug("[selector] inputs for %s: %s -> %s", check_id, ", ".join(shorts), decision)
            return (decision, "selector=false", {})

        # Fallback: use predicate signature names (skip *args/**kwargs)
        sel_sig = inspect.signature(sel)
        kwargs: Dict[str, Any] = {}
        for name, param in sel_sig.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            if name not in FACT_REGISTRY:
                raise Runner.PlanningError(f"unknown fact in selector: {name}")
            try:
                fact_fn = FACT_REGISTRY[name]
                fsig = inspect.signature(fact_fn)
                overrides: Dict[str, Any] = {p: params[p] for p in fsig.parameters if p in params}
                kwargs[name] = self._resolve_fact_with_overrides(name, overrides) if overrides else self._resolve_fact(name)
            except Exception as exc:
                raise Runner.PlanningError(f"fact {name} failed during selector evaluation: {exc}") from exc
        decision = bool(sel(**kwargs))
        # DEBUG: log inputs and decision
        shorts = []
        for n, v in kwargs.items():
            s = repr(v)
            if len(s) > 200:
                s = s[:200] + "..."
            shorts.append(f"{n}={s}")
        self._logger.debug("[selector] inputs for %s: %s -> %s", check_id, ", ".join(shorts), decision)
        return (decision, "selector=false", {})

    # legacy selector helpers removed; predicate-only is supported

    def _resolve_fact_with_overrides(self, fact_id: str, overrides: Dict[str, Any], stack: list[str] | None = None) -> Any:
        """Resolve a fact allowing some parameters to be overridden.

        This does not memoize the result and is used only for selector binding checks.
        """
        if stack is None:
            stack = []
        if fact_id in stack:
            cycle = " -> ".join([*stack, fact_id])
            raise ValueError(f"Cycle detected in facts: {cycle}")
        if fact_id not in FACT_REGISTRY:
            raise KeyError(f"Fact '{fact_id}' is not registered")
        fn = FACT_REGISTRY[fact_id]
        sig = inspect.signature(fn)
        kwargs: Dict[str, Any] = {}
        for name in sig.parameters:
            if name in overrides:
                kwargs[name] = overrides[name]
            else:
                kwargs[name] = self._resolve_fact(name, [*stack, fact_id])
        return fn(**kwargs)

    def _plan_instances(self, check_id: str, check_fn: Callable[..., Any]) -> List[Tuple[str, Dict[str, Any]]]:
        instances = self._expand_params(check_id, check_fn)
        if instances:
            ids = ", ".join(inst_id for inst_id, _ in instances)
            self._logger.debug("[param] expanded %s -> %s", check_id, ids)
        return instances

    def _execute_instances(
        self,
        check_fn: Callable[..., Tuple[Status | str, Any]],
        instances: List[Tuple[str, Dict[str, Any], Dict[str, Dict[str, Any]]]],
        tags: List[str],
    ) -> List[CheckResult]:
        out: list[CheckResult] = []
        for inst_id, param_bindings, fact_overrides in instances:
            try:
                status, evidence = self._run_check_instance(check_fn, param_bindings, fact_overrides)
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

    def _run_check_instance(
        self,
        fn: Callable[..., Tuple[Status | str, Any]],
        params: Dict[str, Any],
        fact_overrides: Dict[str, Dict[str, Any]] | None = None,
    ) -> Tuple[Status, Any]:
        """Resolve facts and fixtures, merge with params, run fn, and teardown fixtures.

        fact_overrides:
        - A per-instance mapping of fact_id -> {arg_name: value} used to override
          the arguments passed when resolving facts that are injected as check
          function parameters.
        - This is populated by selector processing for `requires(...)` selectors,
          where a fact must exist with specific argument bindings. Bind values can
          come from the current check instance's parametrized arguments (e.g.,
          bind={"mount": "path"}) or be constants (e.g., bind={"mount": "/data"}).
        - Overrides are applied only for fact resolution during this check call.
          They are not memoized in the global fact cache, so they won't leak to
          other checks or instances.
        - Rationale: preflight validates selector facts and param sources, but for
          `requires(...)` we must respect per-instance bindings that are only
          known after parametrization. We therefore defer actual bound resolution
          to execution time while still failing fast on unknown fact names.
        """
        sig = inspect.signature(fn)
        kwargs: Dict[str, Any] = {}
        fixture_cache: Dict[str, Any] = {}
        teardowns: list[Callable[[], None]] = []
        if fact_overrides is None:
            fact_overrides = {}

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
                # name is a fact id for check arg resolution
                if name in FACT_REGISTRY:
                    if name in fact_overrides:
                        kwargs[name] = self._resolve_fact_with_overrides(name, fact_overrides[name])
                    else:
                        try:
                            kwargs[name] = self._resolve_fact(name)
                        except KeyError:
                            # If default resolution fails and we have overrides, try them
                            if name in fact_overrides:
                                kwargs[name] = self._resolve_fact_with_overrides(name, fact_overrides[name])
                            else:
                                raise
                else:
                    # Not a fact, but also not a fixture and not in params — treat as error via normal resolution
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
