from __future__ import annotations

from typing import Any

from mr_kot import fact, check, run, Status


class TestFactsResolution:
    def test_fact_dependency_injection(self) -> None:
        @fact
        def a() -> int:
            return 2

        @fact
        def b(a: int) -> int:
            return a + 3

        @check
        def uses_b(b: int):
            return (Status.PASS, b)

        result = run()
        item = next(i for i in result.items if i.id == "uses_b")
        assert item.status == Status.PASS
        assert item.evidence == 5

    def test_fact_multi_level_chain(self) -> None:
        @fact
        def base() -> int:
            return 1

        @fact
        def mid(base: int) -> int:
            return base + 1

        @fact
        def top(mid: int) -> int:
            return mid * 10

        @check
        def uses_top(top: int):
            return (Status.PASS, top)

        result = run()
        item = next(i for i in result.items if i.id == "uses_top")
        assert item.status == Status.PASS
        assert item.evidence == 20

    def test_fact_memoization_single_call(self) -> None:
        calls: list[int] = []

        @fact
        def a() -> int:
            calls.append(1)
            return 7

        @fact
        def b(a: int) -> int:
            return a + 1

        @fact
        def c(a: int) -> int:
            return a + 2

        @check
        def uses_b_c(b: int, c: int):
            return (Status.PASS, (b, c))

        res = run()
        assert res.overall == Status.PASS
        assert calls == [1]  # computed once even if used twice

    def test_fact_not_computed_when_unused(self) -> None:
        @fact
        def used() -> int:
            return 1

        @fact
        def heavy() -> int:  # should not be called
            raise AssertionError("heavy fact should not be computed")

        @check
        def ok(used: int):
            return (Status.PASS, used)

        res = run()
        assert res.overall == Status.PASS

    def test_missing_dependency_marks_error(self) -> None:
        @fact
        def needs_missing(missing: Any) -> int:  # type: ignore[no-redef]
            return 0

        @check
        def user(needs_missing: int):
            return (Status.PASS, needs_missing)

        res = run()
        item = next(i for i in res.items if i.id == "user")
        assert item.status == Status.ERROR

    def test_cycle_detection_between_facts(self) -> None:
        @fact
        def x(y: int) -> int:
            return y

        @fact
        def y(x: int) -> int:
            return x

        @check
        def use_x(x: int):
            return (Status.PASS, x)

        res = run()
        item = next(i for i in res.items if i.id == "use_x")
        assert item.status == Status.ERROR

    def test_fact_exception_marks_dependents_error(self) -> None:
        @fact
        def boom() -> int:
            raise RuntimeError("exploded")

        @check
        def uses_boom(boom: int):
            return (Status.PASS, boom)

        res = run()
        item = next(i for i in res.items if i.id == "uses_boom")
        assert item.status == Status.ERROR


class TestFactsPurityAndStability:
    def test_same_run_returns_same_object_or_value(self) -> None:
        class Obj:
            pass

        @fact
        def base() -> Obj:
            return Obj()

        @fact
        def id1(base: Obj) -> int:
            return id(base)

        @fact
        def id2(base: Obj) -> int:
            return id(base)

        @check
        def compare(id1: int, id2: int):
            return (Status.PASS, id1 == id2)

        res = run()
        item = next(i for i in res.items if i.id == "compare")
        assert item.status == Status.PASS
        assert item.evidence is True

    def test_runner_does_not_precompute_all_facts(self) -> None:
        @fact
        def never() -> int:
            raise AssertionError("should not be precomputed")

        @check
        def ok() -> tuple[Status, str]:
            return (Status.PASS, "ok")

        res = run()
        assert res.overall == Status.PASS
