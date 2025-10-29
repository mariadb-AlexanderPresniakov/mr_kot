"""
Validators are small reusable building blocks of logic used inside checks.
They represent ready-made validation routines for specific domains (for example, files, directories, services, or network resources).
Each validator can be configured with parameters (like expected mode, owner, or recursion) and then applied to a specific target.
Validators return the same result format as a check — a status and evidence — so they can be freely combined.
You can run several validators together with check_all(), which executes them in order and aggregates their results,
  stopping early if one fails (or running all if configured).
This allows you to compose complex checks from small, prepared, domain-specific pieces of logic without writing everything manually.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Protocol, Tuple, Union, runtime_checkable
from dataclasses import dataclass, fields

from .status import Status

# Normalized validator result shape
ValidatorResult = Tuple[Status, str]

# Public protocol: a validator is a callable over a single target that returns (status, evidence), just like checks.
# Note: We allow either Status or str for status to support lightweight implementations; callers should normalize.
Validator = Callable[[Any], Tuple[Union[Status, str], str]]

_SEVERITY = {Status.ERROR: 3, Status.FAIL: 2, Status.WARN: 1, Status.PASS: 0}


@runtime_checkable
class ValidatorFactory(Protocol):
    """Optional typing aid for factories constructing validators with options.

    Example:
        class HasMode:
            def __init__(self, mode: str, recursive: bool = False) -> None: ...
            def __call__(self, target: str) -> tuple[Status, str]: ...
    """

    def __call__(self, *args: Any, **kwargs: Any) -> Validator:
        ...


def _get_logger() -> logging.Logger:
    logger = logging.getLogger("mr_kot")
    # Remove only handlers whose stream has been closed (e.g., prior StreamHandler to a closed stderr)
    for h in list(logger.handlers):
        stream = getattr(h, "stream", None)
        if getattr(stream, "closed", False):
            logger.removeHandler(h)
    logger.propagate = True
    return logger


@dataclass
class BaseValidator:
    """Base class for validators with readable description and robust calling."""

    def validate(self, target: Any) -> Tuple[Status, str]:
        """Implement validator logic here."""
        raise NotImplementedError

    def describe(self) -> str:
        """Return a human-friendly label for diagnostics.

        Default: ClassName(field=value, ...) using dataclass fields.
        """
        cls_name = self.__class__.__name__
        try:
            parts = []
            for f in fields(self):
                val = getattr(self, f.name)
                parts.append(f"{f.name}={val!r}")
            args = ", ".join(parts)
            return f"{cls_name}({args})" if parts else f"{cls_name}()"
        except Exception:
            return f"{cls_name}()"

    def __call__(self, target: Any) -> Tuple[Status, str]:
        """Execute validator with error safety and status normalization.

        - Converts unexpected exceptions to (ERROR, evidence).
        - Normalizes Status if a string value is returned by validate().
        """
        name = _validator_name(self)
        try:
            raw_status, ev = self.validate(target)
            status = _normalize_status(raw_status)
            return (status, ev)
        except Exception as exc:
            return (Status.ERROR, f"validator={name} error={exc.__class__.__name__}: {exc}")


def check_all(target: Any, *validators: Validator, fail_fast: bool = True) -> Tuple[Status, str]:
    """Run validators over a single target and aggregate to one (status, evidence).

    - Execute in order. If fail_fast=True, stop on first FAIL or ERROR.
    - With fail_fast=False, run them all and aggregate by severity: ERROR > FAIL > WARN > PASS.
    - Evidence:
        * fail_fast=True: return evidence from the first FAIL/ERROR (or PASS/WARN if none fail).
        * fail_fast=False: join evidences with "; ". If all PASS, evidence is "target=<repr> ok".
    - Exceptions are caught and converted to ERROR with evidence
      "validator=<name> error=<ExcType>: <message>".
    """
    if not validators:
        return (Status.PASS, f"target={target!r} ok")

    results: list[tuple[Status, str, str]] = []  # (status, evidence, name)
    first_failure_ev: str | None = None

    for v in validators:
        name = _validator_label(v)
        try:
            raw_status, ev = v(target)
            status = _normalize_status(raw_status)
        except Exception as exc:
            status = Status.ERROR
            ev = f"validator={name} error={exc.__class__.__name__}: {exc}"
        # Debug log per-validator
        short = ev if len(ev) <= 500 else ev[:500] + "..."
        _get_logger().debug("[validator] target=%r name=%s status=%s evidence=%s", target, name, status, short)

        results.append((status, ev, name))
        if fail_fast and status in (Status.FAIL, Status.ERROR):
            first_failure_ev = ev
            _get_logger().info("[validator] fail_fast: stopping after name=%s status=%s", name, status)
            break

    if fail_fast:
        # If we hit a failure/error, return that. Otherwise, fold the statuses we did get.
        if first_failure_ev is not None:
            return (results[-1][0], first_failure_ev)
        # No failure encountered; determine worst among executed and craft evidence
        worst = max((s for s, _e, _n in results), key=lambda s: _SEVERITY.get(s, 0))
        # If only one validator, preserve its evidence; if multiple and all PASS, use generic ok
        if len(results) == 1:
            return (results[0][0], results[0][1])
        # Return the first evidence with the worst severity; if all PASS (worst=PASS), return generic ok
        if worst is Status.PASS:
            return (Status.PASS, f"target={target!r} ok")
        for s, e, _n in results:
            if s is worst:
                return (s, e)
        # Fallback
        return (worst, results[0][1])

    # fail_fast=False: aggregate all
    worst = max((s for s, _e, _n in results), key=lambda s: _SEVERITY.get(s, 0))
    if all(s is Status.PASS for s, _e, _n in results):
        return (Status.PASS, f"target={target!r} ok")

    # Join evidences in input order; keep deterministic order
    evidences: list[str] = [e for _s, e, _n in results]
    return (worst, "; ".join(evidences))


def _normalize_status(s: Union[Status, str]) -> Status:
    """Normalize a status to a Status enum value."""
    if isinstance(s, Status):
        return s
    if isinstance(s, str):
        # Allow either enum name or value; current Status both match upper names
        try:
            return Status[s] if s in Status.__members__ else Status(s)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"invalid status: {s}") from exc


def _validator_name(v: Validator) -> str:
    # Try best-effort human-friendly name
    if hasattr(v, "__name__"):
        return str(v.__name__)  # type: ignore[attr-defined]
    cls = v.__class__
    return cls.__name__ if hasattr(cls, "__name__") else repr(v)


def _validator_label(v: Validator) -> str:
    """Human-readable label for a validator for diagnostics.

    Preference order:
    - v.describe() if available and returns a string
    - fallback to _validator_name(v)
    """
    desc = getattr(v, "describe", None)
    if callable(desc):
        try:
            s = desc()
            if isinstance(s, str) and s:
                return s
        except Exception:  # pragma: no cover - defensive
            pass

    return _validator_name(v)


def any_of(*validators: Validator) -> Validator:
    """Compose validators with OR semantics.

    - If any validator passes, return PASS and indicate which one.
    - If none pass, return the most severe status and aggregate all evidences.
    """
    def _v(target: Any) -> Tuple[Status, str]:
        results: list[tuple[Status, str, str]] = []  # (status, evidence, label)
        for v in validators:
            name = _validator_label(v)
            try:
                raw_status, ev = v(target)
                status = _normalize_status(raw_status)
            except Exception as exc:  # pragma: no cover - defensive
                status = Status.ERROR
                ev = f"validator={name} error={exc.__class__.__name__}: {exc}"
            results.append((status, ev, name))
            if status is Status.PASS:
                return (Status.PASS, f"any_of: passed via {name}")

        if not results:
            return (Status.PASS, f"target={target!r} ok")

        worst = max((s for s, _e, _n in results), key=lambda s: _SEVERITY.get(s, 0))
        evidences = "; ".join(f"{n}: {e}" for _s, e, n in results)
        return (worst, f"any_of: no match; {evidences}")

    return _v
