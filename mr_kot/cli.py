from __future__ import annotations

import argparse
import json
import runpy
import sys
from importlib import import_module
from pathlib import Path

from .runner import run as run_checks


def _import_by_arg(arg: str) -> None:
    path = Path(arg)
    if path.suffix == ".py" and path.exists():
        runpy.run_path(str(path), run_name="__main__")
    else:
        # treat as module path (e.g., package.module)
        import_module(arg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mrkot", description="Mr. Kot invariant runner")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run checks from a module or file")
    p_run.add_argument("module", help="Module name or path to .py file to import and run")

    ns = parser.parse_args(argv)

    if ns.command == "run":
        _import_by_arg(ns.module)
        result = run_checks()
        json.dump(result, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
