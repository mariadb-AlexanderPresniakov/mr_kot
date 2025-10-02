from __future__ import annotations

import sys

import pytest

from mr_kot.registry import CHECK_REGISTRY, FACT_REGISTRY, FIXTURE_REGISTRY


@pytest.fixture(autouse=True)
def _reset_registries() -> None:
    FACT_REGISTRY.clear()
    CHECK_REGISTRY.clear()
    FIXTURE_REGISTRY.clear()
    # Also remove any dynamically created modules used in tests to avoid cross-test leakage
    for name in list(sys.modules.keys()):
        if name.startswith("testmod_"):
            sys.modules.pop(name, None)
