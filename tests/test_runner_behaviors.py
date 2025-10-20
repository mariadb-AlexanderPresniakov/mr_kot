from __future__ import annotations

import pytest

from mr_kot.runner import Runner, RunResult, CheckResult
from mr_kot.status import Status


def test_runner_run_converts_top_level_exception_to_error(monkeypatch):
    def boom(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(Runner, "_preflight_selector_and_param_facts", boom, raising=True)

    r = Runner()
    res = r.run()

    assert isinstance(res, RunResult)
    assert res.counts[Status.ERROR] >= 1
    assert res.items
    err = res.items[-1]
    assert err.id == "Runner.run"
    assert err.status == Status.ERROR
    assert "RuntimeError" in str(err.evidence)


def test_runresult_problems_filters_warns_option():
    items = [
        CheckResult(id="a", status=Status.PASS, evidence=None, tags=[]),
        CheckResult(id="b", status=Status.WARN, evidence=None, tags=[]),
        CheckResult(id="c", status=Status.FAIL, evidence=None, tags=[]),
        CheckResult(id="d", status=Status.ERROR, evidence=None, tags=[]),
        CheckResult(id="e", status=Status.SKIP, evidence=None, tags=[]),
    ]
    counts = {s: 0 for s in Status}
    for it in items:
        counts[it.status] += 1

    rr = RunResult(overall=Status.FAIL, counts=counts, items=items)

    ids_default = [it.id for it in rr.problems()]
    assert ids_default == ["c", "d"]

    ids_with_warns = [it.id for it in rr.problems(include_warns=True)]
    assert ids_with_warns == ["b", "c", "d"]
