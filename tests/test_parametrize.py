from __future__ import annotations

from mr_kot import Status, check, fact, fixture, parametrize, run


class TestParametrizeInline:
    def test_inline_expands_to_multiple_instances(self) -> None:
        @check
        @parametrize("path", values=["/data", "/logs"])
        def check_path(path: str):
            return (Status.PASS, path)

        res = run()
        ids = sorted(i["id"] for i in res["items"])
        assert ids == ["check_path[path='/data']", "check_path[path='/logs']"]

    def test_inline_ids_are_stable_and_sorted(self) -> None:
        @check
        @parametrize("v", values=[3, 1, 2])
        def c(v: int):
            return (Status.PASS, v)

        res = run()
        ids = [i["id"] for i in res["items"]]
        # Order should be deterministic by planner expansion order (definition order of values)
        assert ids == ["c[v=3]", "c[v=1]", "c[v=2]"]


class TestParametrizeFromFact:
    def test_expand_from_enumeration_fact(self) -> None:
        @fact
        def services() -> list[str]:
            return ["cron", "sshd"]

        @check
        @parametrize("svc", source="services")
        def svc_present(svc: str):
            return (Status.PASS, svc)

        res = run()
        ids = sorted(i["id"] for i in res["items"])
        assert ids == ["svc_present[svc='cron']", "svc_present[svc='sshd']"]

    def test_empty_enumeration_yields_no_instances(self) -> None:
        @fact
        def vals() -> list[int]:
            return []

        @check
        @parametrize("v", source="vals")
        def c(v: int):
            return (Status.PASS, v)

        res = run()
        # No items emitted
        assert all(not i["id"].startswith("c[") for i in res["items"]) or res["items"] == []

    def test_param_source_must_be_sequence(self) -> None:
        @fact
        def bad() -> int:
            return 5

        @check
        @parametrize("v", source="bad")
        def c(v: int):
            return (Status.PASS, v)

        # Will error when iterating over non-sequence in planner
        res = run()
        item = next(i for i in res["items"] if i["id"].startswith("c"))
        assert item["status"] == "ERROR"


class TestParametrizeCartesian:
    def test_multiple_parametrize_decorators_cartesian_product(self) -> None:
        @check
        @parametrize("iface", values=["eth0", "eth1"])
        @parametrize("mtu", values=[1280, 1500])
        def link_ok(iface: str, mtu: int):
            return (Status.PASS, f"{iface}:{mtu}")

        res = run()
        ids = sorted(i["id"] for i in res["items"])
        assert ids == [
            "link_ok[iface='eth0',mtu=1280]",
            "link_ok[iface='eth0',mtu=1500]",
            "link_ok[iface='eth1',mtu=1280]",
            "link_ok[iface='eth1',mtu=1500]",
        ]

    def test_cartesian_product_order_is_stable(self) -> None:
        @check
        @parametrize("x", values=[1, 2])
        @parametrize("y", values=["a", "b"])
        def c(x: int, y: str):
            return (Status.PASS, f"{x}{y}")

        res = run()
        ids = [i["id"] for i in res["items"]]
        assert ids == ["c[x=1,y='a']", "c[x=1,y='b']", "c[x=2,y='a']", "c[x=2,y='b']"]


class TestParametrizeFixturesInteraction:
    def test_fixture_built_per_param_instance(self) -> None:
        calls: list[str] = []

        @fixture
        def res():
            calls.append("build")
            try:
                yield object()
            finally:
                calls.append("teardown")

        @check
        @parametrize("n", values=[1, 2, 3])
        def c(res, n: int):
            return (Status.PASS, n)

        out = run()
        assert out["overall"] == "PASS"
        # Three instances -> three builds and teardowns
        assert calls == ["build", "teardown", "build", "teardown", "build", "teardown"]

    def test_facts_memoized_across_param_instances(self) -> None:
        calls: list[int] = []

        @fact
        def counter() -> int:
            calls.append(1)
            return 7

        @check
        @parametrize("n", values=[10, 20, 30])
        def uses(counter: int, n: int):
            return (Status.PASS, counter + n)

        res = run()
        assert res["overall"] == "PASS"
        assert calls == [1]  # fact computed once across many instances
