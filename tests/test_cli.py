from __future__ import annotations

import re
from pathlib import Path

from mr_kot.cli import main as cli_main


class TestCLIList:
    def test_list_outputs_all_checks_with_tags(self, tmp_path: Path, capsys) -> None:
        file = tmp_path / "mod_list.py"
        file.write_text(
            """
from mr_kot import check, Status

@check(tags=["a","b"]) 
def c1():
    return (Status.PASS, "ok1")

@check(tags=["x"]) 
def c2():
    return (Status.PASS, "ok2")
"""
        )
        rc = cli_main(["run", str(file), "--list"])  # just list
        assert rc == 0
        out = capsys.readouterr().out.strip().splitlines()
        assert any(line.startswith("c1 ") and "['a', 'b']" in line for line in out)
        assert any(line.startswith("c2 ") and "['x']" in line for line in out)


class TestCLIFiltering:
    def test_run_with_tags_includes_only_matching_checks(self, tmp_path: Path, capsys) -> None:
        file = tmp_path / "mod_cli_tags.py"
        file.write_text(
            """
from mr_kot import check, Status

@check(tags=["db"]) 
def db_ok():
    return (Status.PASS, "db")

@check(tags=["net"]) 
def net_ok():
    return (Status.PASS, "net")
"""
        )
        rc = cli_main(["run", str(file), "--tags", "db"])  # filter to db
        assert rc == 0
        out = capsys.readouterr().out
        # default CLI output is JSON
        assert '"items"' in out
        assert '"db_ok"' in out and '"net_ok"' not in out


class TestCLIHUMANOutput:
    def test_human_output_summary_format(self, tmp_path: Path, capsys) -> None:
        file = tmp_path / "mod_human.py"
        file.write_text(
            """
from mr_kot import check, Status

@check 
def ok():
    return (Status.PASS, "it works")

@check 
def bad():
    return (Status.FAIL, "oops")
"""
        )
        rc = cli_main(["run", str(file), "--human"])  # human readable
        assert rc == 0
        out = capsys.readouterr().out
        # Expect lines like: PASS  ok: it works
        assert re.search(r"^PASS\s+ok: it works$", out, re.MULTILINE)
        assert re.search(r"^FAIL\s+bad: oops$", out, re.MULTILINE)
        assert re.search(r"^OVERALL: ", out, re.MULTILINE)

    def test_human_output_contains_status_and_evidence(self, tmp_path: Path, capsys) -> None:
        file = tmp_path / "mod_human2.py"
        file.write_text(
            """
from mr_kot import check, Status

@check 
def warn():
    return (Status.WARN, "heads up")
"""
        )
        rc = cli_main(["run", str(file), "--human"])  # human readable
        assert rc == 0
        out = capsys.readouterr().out
        assert "WARN" in out and "heads up" in out
