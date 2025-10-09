from __future__ import annotations

import json
from pathlib import Path

from mr_kot import Status, check, run
from mr_kot.cli import main as cli_main
from mr_kot.runner import Runner


class TestTags:
    def test_tag_metadata_present_in_output(self) -> None:
        @check(tags=["storage", "security"])
        def tagged():
            return (Status.PASS, "ok")

        # Use Runner with include_tags=True to expose tags in machine-readable output
        result = Runner(include_tags=True).run()
        item = next(i for i in result.items if i.id.startswith("tagged"))
        assert item.status == Status.PASS
        assert sorted(item.tags) == ["security", "storage"]

    def test_filter_by_single_tag(self, tmp_path: Path, capsys) -> None:
        file = tmp_path / "mod_tags.py"
        file.write_text(
            """
from mr_kot import check, Status

@check(tags=["storage"]) 
def disk_ok():
    return (Status.PASS, "disk")

@check(tags=["network"]) 
def net_ok():
    return (Status.PASS, "net")
"""
        )
        rc = cli_main(["run", str(file), "--tags", "storage"])  # filter
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        ids = [i["id"] for i in data["items"]]
        assert ids == ["disk_ok"]

    def test_filter_by_multiple_tags(self, tmp_path: Path, capsys) -> None:
        file = tmp_path / "mod_tags2.py"
        file.write_text(
            """
from mr_kot import check, Status

@check(tags=["storage"]) 
def disk_ok():
    return (Status.PASS, "disk")

@check(tags=["network"]) 
def net_ok():
    return (Status.PASS, "net")

@check(tags=["security"]) 
def sec_ok():
    return (Status.PASS, "sec")
"""
        )
        rc = cli_main(["run", str(file), "--tags", "security,storage"])  # any-match
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        ids = sorted(i["id"] for i in data["items"])
        assert ids == ["disk_ok", "sec_ok"]

    def test_filter_nonmatching_tag_excludes_all(self, tmp_path: Path, capsys) -> None:
        file = tmp_path / "mod_tags3.py"
        file.write_text(
            """
from mr_kot import check, Status

@check(tags=["storage"]) 
def disk_ok():
    return (Status.PASS, "disk")
"""
        )
        rc = cli_main(["run", str(file), "--tags", "nope"])  # no match
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["items"] == []
