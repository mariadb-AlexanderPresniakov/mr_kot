from __future__ import annotations

from mr_kot import Status, check, fact, run


class TestCheckExecution:
    def test_check_receives_injected_facts(self) -> None:
        @fact
        def info() -> dict[str, str]:
            return {"k": "v"}

        @check
        def c(info: dict[str, str]):
            return (Status.PASS, info["k"])

        res = run()
        item = next(i for i in res["items"] if i["id"] == "c")
        assert item["status"] == "PASS"
        assert item["evidence"] == "v"

    def test_check_invalid_return_shape_is_error(self) -> None:
        @check
        def bad_shape() -> str:
            return "oops"

        res = run()
        item = next(i for i in res["items"] if i["id"] == "bad_shape")
        assert item["status"] == "ERROR"

    def test_check_invalid_status_is_error(self) -> None:
        @check
        def bad_status():
            return ("NOT_A_STATUS", "e")

        res = run()
        item = next(i for i in res["items"] if i["id"] == "bad_status")
        assert item["status"] == "ERROR"

    def test_checks_independent_of_order(self) -> None:
        calls: list[str] = []

        @check
        def first():
            calls.append("first")
            return (Status.PASS, "a")

        @check
        def second():
            calls.append("second")
            return (Status.PASS, "b")

        res = run()
        assert res["overall"] == "PASS"
        # Order of execution shouldn't affect results content
        ids = {i["id"] for i in res["items"]}
        assert ids == {"first", "second"}

    def test_unhandled_exception_in_check_becomes_error(self) -> None:
        @check
        def boom():
            raise RuntimeError("nope")

        res = run()
        item = next(i for i in res["items"] if i["id"] == "boom")
        assert item["status"] == "ERROR"


class TestCheckIdsAndNames:
    def test_stable_ids_from_function_names(self) -> None:
        @check
        def id1():
            return (Status.PASS, "")

        @check
        def id2():
            return (Status.PASS, "")

        res = run()
        ids = [i["id"] for i in res["items"]]
        assert set(ids) == {"id1", "id2"}

    def test_ids_dont_change_with_registration_order(self) -> None:
        @check
        def c2():
            return (Status.PASS, "")

        @check
        def c1():
            return (Status.PASS, "")

        res = run()
        ids = sorted(i["id"] for i in res["items"])  # sort to ignore insertion order
        assert ids == ["c1", "c2"]


class TestEvidenceHandling:
    def test_evidence_can_be_empty_string(self) -> None:
        @check
        def empty():
            return (Status.PASS, "")

        res = run()
        item = next(i for i in res["items"] if i["id"] == "empty")
        assert item["status"] == "PASS"
        assert item["evidence"] == ""

    def test_evidence_long_and_unicode_ok(self) -> None:
        long = "😀" * 1000

        @check
        def long_ev():
            return (Status.WARN, long)

        res = run()
        item = next(i for i in res["items"] if i["id"] == "long_ev")
        assert item["status"] == "WARN"
        assert item["evidence"] == long
