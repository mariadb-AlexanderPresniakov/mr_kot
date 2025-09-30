from __future__ import annotations

from pathlib import Path

from mr_kot import Status, check, run
from mr_kot.cli import main as cli_main


def test_run_api_shape() -> None:
    @check
    def simple():
        return (Status.PASS, "ok")

    result = run()
    assert set(result.keys()) == {"overall", "counts", "items"}
    assert result["overall"] in {"PASS", "FAIL", "WARN"}
    assert all(k in result["counts"] for k in ["PASS", "FAIL", "WARN", "SKIP", "ERROR"])
    assert isinstance(result["items"], list)
    assert all(set(i.keys()) == {"id", "status", "evidence"} for i in result["items"])


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
