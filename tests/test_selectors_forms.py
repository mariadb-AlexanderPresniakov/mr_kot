from __future__ import annotations

import pytest

from mr_kot import ALL, ANY, NOT, Status, check, fact, parametrize
from mr_kot.runner import Runner


class TestPredicateSelectors:
    def test_predicate_true_runs(self) -> None:
        @fact
        def os_release() -> dict[str, str]:
            return {"id": "ubuntu", "version": "22.04"}

        @check(selector=lambda os_release: os_release["id"] == "ubuntu")
        def c(os_release: dict[str, str]):
            return (Status.PASS, os_release["id"])  # type: ignore[index]

        res = Runner().run()
        item = next(i for i in res.items if i.id == "c")
        assert item.status == Status.PASS

    def test_predicate_false_skips(self) -> None:
        @fact
        def flag() -> bool:
            return False

        @check(selector=lambda flag: flag)
        def c():
            return (Status.PASS, "never")

        res = Runner().run()
        item = next(i for i in res.items if i.id == "c")
        assert item.status == Status.SKIP
        assert item.evidence == "selector=false"

    def test_unknown_fact_aborts(self) -> None:
        @check(selector=lambda nope: True)
        def c():
            return (Status.PASS, "")

        with pytest.raises(Runner.PlanningError):
            Runner().run()

    def test_fact_production_error_aborts(self) -> None:
        @fact
        def bad() -> bool:
            raise RuntimeError("boom")

        @check(selector=lambda bad: bad)
        def c():
            return (Status.PASS, "")

        with pytest.raises(Runner.PlanningError):
            Runner().run()

    def test_fixture_not_allowed_in_predicate(self) -> None:
        from mr_kot import fixture

        @fixture
        def client():
            return object()

        @check(selector=lambda client: True)
        def c():
            return (Status.PASS, "")

        with pytest.raises(Runner.PlanningError):
            Runner().run()


class TestHelperPredicates:
    def test_all_true_runs(self) -> None:
        @fact
        def a() -> bool:
            return True

        @fact
        def b() -> bool:
            return 1 == 1

        @check(selector=ALL("a", "b"))
        def c():
            return (Status.PASS, "ok")

        res = Runner().run()
        assert res.overall == Status.PASS

    def test_all_one_false_skips(self) -> None:
        @fact
        def a() -> bool:
            return True

        @fact
        def b() -> bool:
            return False

        @check(selector=ALL("a", "b"))
        def c():
            return (Status.PASS, "ok")

        res = Runner().run()
        item = next(i for i in res.items if i.id == "c")
        assert item.status == Status.SKIP

    def test_any_one_true_runs(self) -> None:
        @fact
        def a() -> bool:
            return False

        @fact
        def b() -> bool:
            return True

        @check(selector=ANY("a", "b"))
        def c():
            return (Status.PASS, "ok")

        res = Runner().run()
        assert res.overall == Status.PASS

    def test_any_all_false_skips(self) -> None:
        @fact
        def a() -> bool:
            return False

        @fact
        def b() -> bool:
            return False

        @check(selector=ANY("a", "b"))
        def c():
            return (Status.PASS, "ok")

        res = Runner().run()
        item = next(i for i in res.items if i.id == "c")
        assert item.status == Status.SKIP

    def test_not_negates(self) -> None:
        @fact
        def flag() -> bool:
            return True

        @check(selector=NOT(lambda flag: flag))
        def c():
            return (Status.PASS, "ok")

        res = Runner().run()
        item = next(i for i in res.items if i.id == "c")
        assert item.status == Status.SKIP

    def test_helper_unknown_fact_aborts(self) -> None:
        @check(selector=ALL("missing"))
        def c():
            return (Status.PASS, "")

        with pytest.raises(Runner.PlanningError):
            Runner().run()

    def test_helper_fact_raises_aborts(self) -> None:
        @fact
        def bad() -> bool:
            raise RuntimeError("boom")

        @check(selector=ANY("bad"))
        def c():
            return (Status.PASS, "")

        with pytest.raises(Runner.PlanningError):
            Runner().run()

    def test_param_binding_with_helpers(self) -> None:
        calls: list[str] = []

        @fact
        def present(mount: str) -> bool:
            calls.append(mount)
            return mount == "/data"

        @parametrize("mount", values=["/data", "/logs"])
        @check(selector=ALL("present"))
        def c(mount: str):
            return (Status.PASS, mount)

        res = Runner().run()
        ids = sorted(i.id for i in res.items)
        assert ids == ["c[mount='/data']", "c[mount='/logs']"]
        # present() called once per instance with same-named param binding
        assert calls == ["/data", "/logs"]
