from __future__ import annotations

import os
import sys

import pytest

# Ensure local package import wins over an installed distribution
_HERE = os.path.dirname(__file__)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

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

