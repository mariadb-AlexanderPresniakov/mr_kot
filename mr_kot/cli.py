from __future__ import annotations

import argparse
import json
import runpy
import sys
from importlib import import_module
from pathlib import Path

from .runner import Runner
from .registry import CHECK_REGISTRY


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
    p_run.add_argument("--list", action="store_true", help="List discovered checks and exit")
    p_run.add_argument("--tags", type=str, default="", help="Comma-separated tags to include")
    p_run.add_argument("--human", action="store_true", help="Print human-readable output instead of JSON")
    p_run.add_argument("--verbose", action="store_true", help="Enable DEBUG logging to stderr")

    ns = parser.parse_args(argv)

    if ns.command == "run":
        _import_by_arg(ns.module)
        # Handle --list
        if ns.list:
            for cid, fn in sorted(CHECK_REGISTRY.items(), key=lambda kv: kv[0]):
                tags = getattr(fn, "_mrkot_tags", []) or []
                sys.stdout.write(f"{cid} {tags}\n")
            return 0

        # Tags filtering
        tagset: set[str] | None = None
        if ns.tags:
            tagset = {t.strip() for t in ns.tags.split(",") if t.strip()}

        # Run
        runner = Runner(allowed_tags=tagset, include_tags=True, verbose=ns.verbose)
        result = runner.run()
        if ns.human:
            for item in result.get("items", []):
                sys.stdout.write(f"{item['status']:<5} {item['id']}: {item['evidence']}\n")
            sys.stdout.write(f"OVERALL: {result.get('overall')}\n")
        else:
            json.dump(result, sys.stdout, ensure_ascii=False)
            sys.stdout.write("\n")
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
