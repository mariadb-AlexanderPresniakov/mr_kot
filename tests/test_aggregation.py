from __future__ import annotations

from mr_kot import Status, check, run


class TestAggregation:
    def test_all_pass(self) -> None:
        @check
        def c1():
            return (Status.PASS, "")

        @check
        def c2():
            return (Status.PASS, "")

        res = run()
        assert res.overall == Status.PASS
        assert res.counts[Status.PASS] == 2
        assert res.counts[Status.FAIL] == 0

    def test_warn_sets_overall_warn(self) -> None:
        @check
        def ok():
            return (Status.PASS, "")

        @check
        def warn():
            return (Status.WARN, "w")

        res = run()
        assert res.overall == Status.WARN
        assert res.counts[Status.WARN] == 1

    def test_fail_sets_overall_fail(self) -> None:
        @check
        def ok():
            return (Status.PASS, "")

        @check
        def bad():
            return (Status.FAIL, "no")

        res = run()
        assert res.overall == Status.FAIL
        assert res.counts[Status.FAIL] == 1

    def test_error_counts_as_fail_severity(self) -> None:
        @check
        def boom():
            raise RuntimeError("boom")

        res = run()
        assert res.overall == Status.FAIL
        assert res.counts[Status.ERROR] == 1

    def test_skip_does_not_affect_overall(self) -> None:
        @check
        def skip():
            return (Status.SKIP, "reason")

        res = run()
        assert res.overall == Status.PASS  # only SKIP present does not worsen
        assert res.counts[Status.SKIP] == 1
