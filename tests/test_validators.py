from __future__ import annotations

from mr_kot import Status, check_all


def _pass(msg: str):
    def _v(_t):
        return (Status.PASS, msg)

    _v.__name__ = f"pass_{msg}"
    return _v


def _fail(msg: str):
    def _v(_t):
        return (Status.FAIL, msg)

    _v.__name__ = f"fail_{msg}"
    return _v


def _warn(msg: str):
    def _v(_t):
        return (Status.WARN, msg)

    _v.__name__ = f"warn_{msg}"
    return _v


class TestCheckAll:
    def test_check_all_pass_all(self) -> None:
        status, evidence = check_all("X", _pass("ok1"), _pass("ok2"))
        assert status is Status.PASS
        assert evidence == "target='X' ok"

    def test_check_all_fail_fast_stops_on_fail(self) -> None:
        v1 = _pass("ok")
        v2 = _fail("bad")
        v3_called = False

        def v3(_t):
            nonlocal v3_called
            v3_called = True
            return (Status.PASS, "ok")

        v3.__name__ = "v3"
        status, evidence = check_all("Y", v1, v2, v3, fail_fast=True)
        assert status is Status.FAIL and evidence == "bad"
        assert not v3_called, "third validator should not execute in fail_fast"

    def test_check_all_fail_fast_stops_on_error(self) -> None:

        def err(_t):
            return (Status.ERROR, "boom")

        err.__name__ = "err"
        status, evidence = check_all("Z", err, _pass("ok"), fail_fast=True)
        assert status is Status.ERROR and evidence == "boom"

    def test_check_all_collect_all_aggregates(self) -> None:
        # FAIL dominates WARN and PASS; evidence joined deterministically
        status, evidence = check_all(
            "T",
            _pass("p1"),
            _warn("w1"),
            _fail("f1"),
            _warn("w2"),
            fail_fast=False,
        )
        assert status is Status.FAIL
        assert evidence == "p1; w1; f1; w2"

        # ERROR dominates FAIL
        status2, evidence2 = check_all("T", _fail("f"), _pass("p"), lambda _t: (Status.ERROR, "e"), fail_fast=False)
        assert status2 is Status.ERROR
        assert evidence2 == "f; p; e"

    def test_check_all_catches_exceptions_as_error(self) -> None:
        def boom(_t):
            raise RuntimeError("kaput")

        boom.__name__ = "boom"
        status, evidence = check_all("A", boom)
        assert status is Status.ERROR
        assert "validator=boom error=RuntimeError: kaput" in evidence

    def test_validator_factory_custom_args(self) -> None:
        class HasPrefix:
            def __init__(self, prefix: str) -> None:
                self.prefix = prefix

            def __call__(self, target: str):
                if str(target).startswith(self.prefix):
                    return (Status.PASS, f"{target} has prefix {self.prefix}")
                return (Status.FAIL, f"{target} missing prefix {self.prefix}")

        v = HasPrefix("abc")
        status, evidence = check_all("abcdef", v)
        assert status is Status.PASS and "has prefix abc" in evidence
        status2, _ = check_all("zzz", v)
        assert status2 is Status.FAIL

    
