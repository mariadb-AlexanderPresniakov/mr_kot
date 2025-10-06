from __future__ import annotations

import re
from typing import Any

import pytest

from mr_kot import Status, check, depends, fact, fixture, run
from mr_kot.runner import Runner


class TestDependsBasics:
    def test_depends_fixture_build_and_teardown_without_param(self) -> None:
        calls: list[str] = []

        @fixture
        def res():
            calls.append("build")
            try:
                yield object()
            finally:
                calls.append("teardown")

        @depends("res")
        @check
        def c():
            return (Status.PASS, "ok")

        out = run()
        item = next(i for i in out["items"] if i["id"] == "c")
        assert item["status"] == "PASS"
        assert calls == ["build", "teardown"]

    def test_depends_fact_resolved_without_param(self) -> None:
        calls: list[str] = []

        @fact
        def cfg() -> dict[str, int]:
            calls.append("cfg")
            return {"v": 1}

        @depends("cfg")
        @check
        def c():
            return (Status.PASS, "ok")

        out = run()
        item = next(i for i in out["items"] if i["id"] == "c")
        assert item["status"] == "PASS"
        assert calls == ["cfg"]

    def test_depends_unknown_name_is_planning_error(self) -> None:
        @depends("no_such")
        @check
        def c():
            return (Status.PASS, "ok")

        with pytest.raises(Runner.PlanningError):
            Runner().run()

    def test_depends_fact_failure_marks_error_instance(self) -> None:
        @fact
        def bad() -> int:
            raise RuntimeError("boom")

        @depends("bad")
        @check
        def c():
            return (Status.PASS, "never")

        out = run()
        item = next(i for i in out["items"] if i["id"] == "c")
        assert item["status"] == "ERROR"
        assert "depends failed" in item["evidence"]

    def test_depends_fixture_failure_marks_error_instance_and_teardown_prior(self) -> None:
        calls: list[str] = []

        @fixture
        def ok():
            calls.append("ok+")
            try:
                yield 1
            finally:
                calls.append("ok-")

        @fixture
        def broken():
            raise RuntimeError("nope")

        @depends("ok", "broken")
        @check
        def c():
            return (Status.PASS, "never")

        out = run()
        item = next(i for i in out["items"] if i["id"] == "c")
        assert item["status"] == "ERROR"
        # ok teardown must have run even though broken failed to build
        assert calls == ["ok+", "ok-"]

    def test_depends_with_normal_param_coexists(self) -> None:
        @fact
        def config() -> dict[str, str]:
            return {"k": "v"}

        @depends("config")
        @check
        def c(config: dict[str, str]):
            return (Status.PASS, config["k"])  # type: ignore[index]

        out = run()
        item = next(i for i in out["items"] if i["id"] == "c")
        assert item["status"] == "PASS"
        assert item["evidence"] == "v"


class TestDependsLogging:
    def test_logging_depends_info_debug_lines(self, capsys: Any) -> None:
        @fact
        def f1() -> int:
            return 7

        @fixture
        def fx():
            yield "X"

        @depends("f1", "fx")
        @check
        def c():
            return (Status.PASS, "ok")

        Runner(verbose=True).run()
        captured = capsys.readouterr().err
        # INFO line listing depends
        assert re.search(r"\[depends\] check=c names=\[f1,fx\]", captured)
        # DEBUG lines for each type
        assert re.search(r"\[depends\] fact f1 resolved=", captured)
        assert re.search(r"\[depends\] fixture fx built=", captured)
