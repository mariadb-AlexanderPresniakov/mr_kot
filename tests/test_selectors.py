from __future__ import annotations

import pytest

from mr_kot import Status, check, fact, run
from mr_kot.runner import Runner


class TestSelectorsBasic:
    def test_selector_true_includes_check(self) -> None:
        @fact
        def os_release() -> dict:
            return {"id": "ubuntu"}

        @check(selector=lambda os_release: os_release["id"] == "ubuntu")
        def c(os_release: dict):
            return (Status.PASS, os_release["id"])  # should run

        res = run()
        items = [i for i in res.items if i.id.startswith("c")]
        assert len(items) == 1
        assert items[0].status == Status.PASS

    def test_selector_false_excludes_check(self) -> None:
        @fact
        def os_release() -> dict:
            return {"id": "ubuntu"}

        @check(selector=lambda os_release: False)
        def c(os_release: dict):
            return (Status.PASS, "never")

        res = run()
        # Selector=false emits a SKIP item noting selector=false
        items = [i for i in res.items if i.id == "c"]
        assert len(items) == 1
        assert items[0].status == Status.SKIP
        assert items[0].evidence == "selector=false"

    def test_selector_exception_marks_error(self) -> None:
        @fact
        def os_release() -> dict:
            return {"id": "ubuntu"}

        def boom_selector(os_release: dict) -> bool:
            raise RuntimeError("boom")

        @check(selector=boom_selector)
        def c(os_release: dict):
            return (Status.PASS, "never")

        res = run()
        items = [i for i in res.items if i.id == "c"]
        assert len(items) == 1
        assert items[0].status == Status.ERROR
        assert "boom" in str(items[0].evidence).lower()


class TestSelectorsFactsOnly:
    def test_selector_rejects_fixtures(self) -> None:
        from mr_kot import fixture

        @fixture
        def client():
            return object()

        @check(selector=lambda client: True)  # invalid: using fixture in selector
        def c():
            return (Status.PASS, "")

        with pytest.raises(Runner.PlanningError):
            Runner().run()

    def test_selector_resolves_only_needed_facts(self) -> None:
        calls = []

        @fact
        def a() -> int:
            calls.append("A")
            return 1

        @fact
        def b() -> int:
            raise AssertionError("B must not be resolved during selector")

        @check(selector=lambda a: a == 1)
        def c(a: int):
            return (Status.PASS, a)

        res = run()
        assert res.overall == Status.PASS
        assert calls == ["A"]  # only A computed during selector + later when needed (memoized)


class TestSelectorsMemoizationAndIsolation:
    def test_selector_fact_computed_once_even_for_many_checks(self) -> None:
        calls = []

        @fact
        def counter() -> int:
            calls.append(1)
            return 42

        @check(selector=lambda counter: True)
        def c1(counter: int):
            return (Status.PASS, counter)

        @check(selector=lambda counter: True)
        def c2(counter: int):
            return (Status.PASS, counter)

        res = run()
        assert res.overall == Status.PASS
        assert calls == [1]  # computed once; reused for both selector and checks
