from __future__ import annotations

from typing import Any

from mr_kot import Status, check, fact, fixture, run


class TestFixturesInjection:
    def test_fixture_return_injected_into_check(self) -> None:
        @fixture
        def client() -> dict[str, str]:
            return {"v": "ok"}

        @check
        def c(client: dict[str, str]):
            return (Status.PASS, client["v"])  # type: ignore[index]

        res = run()
        item = next(i for i in res["items"] if i["id"] == "c")
        assert item["status"] == "PASS"
        assert item["evidence"] == "ok"

    def test_fixture_yield_teardown_runs(self) -> None:
        calls: list[str] = []

        @fixture
        def res():
            calls.append("build")
            try:
                yield object()
            finally:
                calls.append("teardown")

        @check
        def c(res: Any):
            return (Status.PASS, "x")

        res_out = run()
        assert res_out["overall"] == "PASS"
        assert calls == ["build", "teardown"]

    def test_fixture_per_check_scope_fresh_instance(self) -> None:
        seen: set[int] = set()

        @fixture
        def obj():
            class Cl:  # simple distinct instances
                pass
            return Cl()

        @check
        def c1(obj):
            seen.add(id(obj))
            return (Status.PASS, "")

        @check
        def c2(obj):
            seen.add(id(obj))
            return (Status.PASS, "")

        res = run()
        assert res["overall"] == "PASS"
        assert len(seen) == 2  # fresh per check instance

    def test_fixture_teardown_runs_on_check_exception(self) -> None:
        calls: list[str] = []

        @fixture
        def res():
            calls.append("build")
            try:
                yield 1
            finally:
                calls.append("teardown")

        @check
        def boom(res):
            raise RuntimeError("oops")

        out = run()
        item = next(i for i in out["items"] if i["id"] == "boom")
        assert item["status"] == "ERROR"
        assert calls == ["build", "teardown"]


class TestFixturesDeps:
    def test_fixture_can_depend_on_fact(self) -> None:
        @fact
        def config() -> dict[str, int]:
            return {"mtu": 1500}

        @fixture
        def mtu(config: dict[str, int]) -> int:
            return config["mtu"]

        @check
        def c(mtu: int):
            return (Status.PASS, mtu)

        res = run()
        item = next(i for i in res["items"] if i["id"] == "c")
        assert item["status"] == "PASS"
        assert item["evidence"] == 1500

    def test_fixture_can_depend_on_fixture_simple(self) -> None:
        calls: list[str] = []

        @fixture
        def base():
            calls.append("b+")
            try:
                yield "B"
            finally:
                calls.append("b-")

        @fixture
        def derived(base: str):  # type: ignore[annotation-unchecked]
            calls.append("d+")
            try:
                yield base + ":D"
            finally:
                calls.append("d-")

        @check
        def c(derived: str):
            return (Status.PASS, derived)

        res = run()
        item = next(i for i in res["items"] if i["id"] == "c")
        assert item["status"] == "PASS"
        assert item["evidence"] == "B:D"
        assert calls == ["b+", "d+", "d-", "b-"]  # reverse teardown order


class TestFixturesSelectorBoundary:
    def test_fixture_not_resolved_during_selector_evaluation(self) -> None:
        @fixture
        def will_raise():
            raise AssertionError("should not build in selector phase")

        @fact
        def a() -> int:
            return 1

        @check(selector=lambda a: a == 1)
        def c():
            return (Status.PASS, "ok")

        res = run()
        item = next(i for i in res["items"] if i["id"] == "c")
        assert item["status"] == "PASS"
