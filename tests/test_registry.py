from __future__ import annotations

import pytest

from mr_kot import check, fact
from mr_kot.registry import CHECK_REGISTRY, FACT_REGISTRY


class TestRegistry:
    def test_register_fact_by_name(self) -> None:
        @fact
        def alpha() -> int:
            return 1

        assert "alpha" in FACT_REGISTRY
        assert FACT_REGISTRY["alpha"] is alpha

    def test_register_check_by_name(self) -> None:
        @check
        def beta() -> tuple[str, str]:
            return ("PASS", "ok")

        assert "beta" in CHECK_REGISTRY
        assert CHECK_REGISTRY["beta"] is beta

    def test_register_non_decorated_not_present(self) -> None:
        def gamma() -> None:
            pass

        assert "gamma" not in FACT_REGISTRY
        assert "gamma" not in CHECK_REGISTRY

    def test_register_duplicate_fact_name_raises(self) -> None:
        @fact
        def delta() -> int:
            return 1

        def delta() -> int:  # type: ignore[no-redef]  # noqa: F811 - intentional redefinition for test
            return 2

        with pytest.raises(ValueError):
            fact(delta)  # type: ignore[arg-type]

    def test_register_same_function_twice_noop(self) -> None:
        @fact
        def epsilon() -> int:
            return 1

        # second decoration is effectively a noop; should not raise
        fact(epsilon)
        assert FACT_REGISTRY["epsilon"] is epsilon

    # Optional early guardrails
    def test_fact_id_equals_function_name(self) -> None:
        @fact
        def zeta_name() -> int:
            return 0

        assert list(FACT_REGISTRY.keys()) == ["zeta_name"]

    def test_check_id_equals_function_name(self) -> None:
        @check
        def eta_name() -> tuple[str, str]:
            return ("PASS", "ok")

        assert list(CHECK_REGISTRY.keys()) == ["eta_name"]
