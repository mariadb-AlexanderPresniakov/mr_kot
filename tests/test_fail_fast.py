from __future__ import annotations

import pytest

from mr_kot import Status, check, parametrize, run


class TestFailFast:
    def test_fail_fast_triggers_on_fail(self, capsys: pytest.CaptureFixture[str]) -> None:
        @check
        @parametrize("v", values=[1, 2, 3], fail_fast=True)
        def c(v: int):
            if v == 1:
                return (Status.FAIL, "bad")
            return (Status.PASS, v)

        res = run()
        # Expect first FAIL, remaining SKIP
        ids_status = [(i.id, i.status, i.evidence) for i in res.items]
        assert ids_status[0][0] == "c[v=1]" and ids_status[0][1] == Status.FAIL
        assert ids_status[1] == ("c[v=2]", Status.SKIP, "skipped due to fail_fast after previous failure")
        assert ids_status[2] == ("c[v=3]", Status.SKIP, "skipped due to fail_fast after previous failure")

        # Log contains the info line
        stderr = capsys.readouterr().err
        assert "[parametrize] fail_fast: stopping remaining instances of c after c[v=1] failed." in stderr

    def test_fail_fast_triggers_on_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        @check
        @parametrize("v", values=[1, 2, 3], fail_fast=True)
        def c(v: int):
            if v == 1:
                raise RuntimeError("boom")
            return (Status.PASS, v)

        res = run()
        items = res.items
        assert items[0].id == "c[v=1]" and items[0].status == Status.ERROR
        assert items[1].id == "c[v=2]" and items[1].status == Status.SKIP and items[1].evidence == "skipped due to fail_fast after previous failure"
        assert items[2].id == "c[v=3]" and items[2].status == Status.SKIP and items[2].evidence == "skipped due to fail_fast after previous failure"

        stderr = capsys.readouterr().err
        assert "[parametrize] fail_fast: stopping remaining instances of c after c[v=1] failed." in stderr

    def test_fail_fast_off_executes_all(self) -> None:
        @check
        @parametrize("v", values=[1, 2, 3], fail_fast=False)
        def c(v: int):
            if v == 1:
                return (Status.FAIL, "bad")
            return (Status.PASS, v)

        res = run()
        # All should run; no skips due to fail_fast
        statuses = [i.status for i in res.items]
        assert statuses == [Status.FAIL, Status.PASS, Status.PASS]

    def test_fail_fast_logs_event(self, capsys: pytest.CaptureFixture[str]) -> None:
        @check
        @parametrize("x", values=["a", "b"], fail_fast=True)
        def c(x: str):
            return (Status.ERROR, "err") if x == "a" else (Status.PASS, x)

        _ = run()
        stderr = capsys.readouterr().err
        assert "[parametrize] fail_fast: stopping remaining instances of c after c[x='a'] failed." in stderr

    def test_fail_fast_result_counts_correct(self) -> None:
        @check
        @parametrize("n", values=[0, 1, 2, 3], fail_fast=True)
        def c(n: int):
            if n == 1:
                return (Status.FAIL, "oops")
            return (Status.PASS, n)

        res = run()
        # Expect: PASS for n=0, FAIL for n=1, SKIP for n=2 and n=3
        assert res.counts[Status.PASS] == 1
        assert res.counts[Status.FAIL] == 1
        assert res.counts[Status.SKIP] == 2
        assert res.counts[Status.ERROR] == 0
