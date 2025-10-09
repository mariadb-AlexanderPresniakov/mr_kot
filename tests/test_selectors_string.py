from __future__ import annotations

import pytest

from mr_kot import Status, check, fact
from mr_kot.runner import Runner


def test_selector_string_single_fact_true_runs() -> None:
    @fact
    def flag() -> bool:
        return True

    @check(selector="flag")
    def c():
        return (Status.PASS, "ok")

    res = Runner().run()
    item = next(i for i in res["items"] if i["id"] == "c")
    assert item["status"] == "PASS"


def test_selector_string_single_fact_false_skips() -> None:
    @fact
    def flag() -> bool:
        return False

    @check(selector="flag")
    def c():
        return (Status.PASS, "never")

    res = Runner().run()
    item = next(i for i in res["items"] if i["id"] == "c")
    assert item["status"] == "SKIP"
    assert item["evidence"] == "selector=false"


def test_selector_string_multiple_facts_all_true_runs() -> None:
    @fact
    def is_ubuntu() -> bool:
        return True

    @fact
    def has_systemd() -> bool:
        return 1  # truthy

    @check(selector="is_ubuntu, has_systemd")
    def c():
        return (Status.PASS, "ok")

    res = Runner().run()
    item = next(i for i in res["items"] if i["id"] == "c")
    assert item["status"] == "PASS"


def test_selector_string_multiple_facts_one_false_skips() -> None:
    @fact
    def is_ubuntu() -> bool:
        return True

    @fact
    def has_systemd() -> bool:
        return 0  # falsy

    @check(selector="is_ubuntu,has_systemd")
    def c():
        return (Status.PASS, "never")

    res = Runner().run()
    item = next(i for i in res["items"] if i["id"] == "c")
    assert item["status"] == "SKIP"


def test_selector_string_invalid_format_raises() -> None:
    with pytest.raises(ValueError):
        @check(selector="is_ubuntu,,has_systemd")
        def c():
            return (Status.PASS, "")


def test_selector_callable_still_supported() -> None:
    @fact
    def flag() -> bool:
        return True

    @check(selector=lambda flag: flag)
    def c():
        return (Status.PASS, "ok")

    res = Runner().run()
    item = next(i for i in res["items"] if i["id"] == "c")
    assert item["status"] == "PASS"
