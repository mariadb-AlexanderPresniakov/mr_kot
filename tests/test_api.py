from __future__ import annotations

from pathlib import Path

from mr_kot import Status, check, run
from mr_kot.cli import main as cli_main


def test_run_api_shape() -> None:
    @check
    def simple():
        return (Status.PASS, "ok")

    result = run()
    # RunResult dataclass shape
    from mr_kot.runner import RunResult, CheckResult

    assert isinstance(result, RunResult)
    assert hasattr(result, "overall") and hasattr(result, "counts") and hasattr(result, "items")
    assert result.overall in {Status.PASS, Status.FAIL, Status.WARN}
    # counts contain all statuses as keys
    for k in [Status.PASS, Status.FAIL, Status.WARN, Status.SKIP, Status.ERROR]:
        assert k in result.counts
    # items are CheckResult instances
    assert isinstance(result.items, list)
    assert all(isinstance(i, CheckResult) for i in result.items)


def test_cli_run_with_temp_module(tmp_path) -> None:
    file: Path = tmp_path / "mod.py"
    file.write_text(
        """
from mr_kot import check, Status

@check
def hello():
    return (Status.PASS, "hello")
"""
    )

    # Invoke CLI main with the temp file
    rc = cli_main(["run", str(file)])
    assert rc == 0
