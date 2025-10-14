from __future__ import annotations

import logging
import os
import sys

import pytest

# Ensure local package import wins over an installed distribution
_HERE = os.path.dirname(__file__)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from mr_kot import LOGGER_NAME  # noqa: E402
from mr_kot.registry import CHECK_REGISTRY, FACT_REGISTRY, FIXTURE_REGISTRY  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_registries() -> None:
    FACT_REGISTRY.clear()
    CHECK_REGISTRY.clear()
    FIXTURE_REGISTRY.clear()
    # Also remove any dynamically created modules used in tests to avoid cross-test leakage
    for name in list(sys.modules.keys()):
        if name.startswith("testmod_"):
            sys.modules.pop(name, None)


@pytest.fixture()
def mr_kot_stderr_logging() -> None:
    """Configure mr_kot logger to emit to stderr at DEBUG with a simple formatter.

    Use this fixture in tests that assert on mr_kot's log output.
    """
    lg = logging.getLogger(LOGGER_NAME)
    prev_handlers = list(lg.handlers)
    prev_level = lg.level
    prev_propagate = lg.propagate
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    lg.handlers = [handler]
    lg.setLevel(logging.DEBUG)
    lg.propagate = False
    try:
        yield
    finally:
        lg.handlers = prev_handlers
        lg.setLevel(prev_level)
        lg.propagate = prev_propagate

