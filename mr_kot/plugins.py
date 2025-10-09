from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from importlib import import_module, metadata
from typing import Iterable, List, Tuple, Set

from .registry import CHECK_REGISTRY, FACT_REGISTRY, FIXTURE_REGISTRY

_LOGGER_NAME = "mr_kot"


class PluginLoadError(Exception):
    pass


@dataclass
class RegistryView:
    facts: Set[str]
    fixtures: Set[str]
    checks: Set[str]


def _get_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    # Reinitialize handler to bind to current sys.stderr (helps with test capture)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    return logger


def discover_entrypoint_plugins() -> List[Tuple[str, str]]:
    """Return a list of (name, module_path) for entry points group 'mr_kot.plugins'.

    This does not import the modules.
    """
    eps: Iterable
    try:
        # Python 3.10+
        eps = metadata.entry_points().select(group="mr_kot.plugins")  # type: ignore[attr-defined]
        items = [(ep.name, ep.value) for ep in eps]  # type: ignore[attr-defined]
    except Exception:
        # Fallback to older API
        _get_logger().error("[plugins] entry_points().select failed, trying legacy API")
        # Python 3.8-3.9 compatibility
        try:
            groups = metadata.entry_points()  # type: ignore[assignment]
            group_list = groups.get("mr_kot.plugins", [])  # type: ignore[union-attr]
            items = [(ep.name, ep.value) for ep in group_list]
        except Exception as exc:
            _get_logger().error("[plugins] entry_points() legacy access failed: %s: %s", exc.__class__.__name__, exc)
            items = []
    return sorted(items, key=lambda kv: kv[0])


def _snapshot() -> RegistryView:
    return RegistryView(
        facts=set(FACT_REGISTRY.keys()),
        fixtures=set(FIXTURE_REGISTRY.keys()),
        checks=set(CHECK_REGISTRY.keys()),
    )


def _import_module_with_stats(module_path: str, logger: logging.Logger) -> RegistryView:
    before = _snapshot()
    logger.info("[plugins] loading module=%s", module_path)
    try:
        import_module(module_path)
    except Exception as exc:
        # Preserve duplicate ID collisions (ValueError from registry) for callers/tests
        if isinstance(exc, ValueError):
            raise
        raise PluginLoadError(f"failed to import plugin module '{module_path}': {exc.__class__.__name__}: {exc}") from exc
    after = _snapshot()
    new_facts = sorted(after.facts - before.facts)
    new_fixes = sorted(after.fixtures - before.fixtures)
    new_checks = sorted(after.checks - before.checks)
    logger.info(
        "[plugins] loaded module=%s facts=%d fixtures=%d checks=%d",
        module_path, len(new_facts), len(new_fixes), len(new_checks)
    )
    if new_facts:
        logger.debug("[plugins] new facts: %s", ", ".join(new_facts))
    if new_fixes:
        logger.debug("[plugins] new fixtures: %s", ", ".join(new_fixes))
    if new_checks:
        logger.debug("[plugins] new checks: %s", ", ".join(new_checks))
    return RegistryView(facts=set(new_facts), fixtures=set(new_fixes), checks=set(new_checks))


def load_plugins(explicit_modules: List[str] | None = None, *, verbose: bool = False) -> None:
    """Load plugins from explicit module paths and entry points.

    - Import CLI-specified plugins first, in order.
    - Then import entry-point plugins sorted by entry point name.
    - Deduplicate by module path.
    - Abort on any import error.
    """
    logger = _get_logger(verbose)

    loaded: set[str] = set()

    # Explicit list
    for mod in (explicit_modules or []):
        if mod in loaded:
            continue
        _import_module_with_stats(mod, logger)
        loaded.add(mod)

    # Entry points
    eps = discover_entrypoint_plugins()
    logger.info("[plugins] discovered %d entry-point plugins", len(eps))
    for _name, module_path in eps:
        if module_path in loaded:
            continue
        _import_module_with_stats(module_path, logger)
        loaded.add(module_path)
