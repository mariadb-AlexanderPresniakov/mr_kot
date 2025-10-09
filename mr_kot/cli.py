from __future__ import annotations

import argparse
import json
import runpy
import sys
from importlib import import_module
from pathlib import Path
from typing import List, Optional, Set

from .plugins import (
    PluginLoadError,
    discover_entrypoint_plugins,
    load_plugins,
)
from .registry import CHECK_REGISTRY
from .runner import Runner


def _import_by_arg(arg: str) -> None:
    path = Path(arg)
    if path.suffix == ".py" and path.exists():
        runpy.run_path(str(path), run_name="__main__")
    else:
        # treat as module path (e.g., package.module)
        import_module(arg)

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="mrkot", description="Mr. Kot, invariant checker")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run checks from a module or file")
    p_run.add_argument("module", help="Module name or path to .py file to import and run")
    p_run.add_argument("--list", action="store_true", help="List discovered checks and exit")
    p_run.add_argument("--tags", type=str, default="", help="Comma-separated tags to include")
    p_run.add_argument("--human", action="store_true", help="Print human-readable output instead of JSON")
    p_run.add_argument("--verbose", action="store_true", help="Enable DEBUG logging to stderr")
    p_run.add_argument("--plugins", type=str, default="", help="Comma-separated plugin modules to import first")

    p_plugins = sub.add_parser("plugins", help="Plugins commands")
    p_plugins.add_argument("--list", action="store_true", help="List discovered entry-point plugins and exit")

    ns = parser.parse_args(argv)

    if ns.command == "run":
        # Load plugins: explicit first, then entry points
        explicit = [m.strip() for m in (ns.plugins or "").split(",") if m.strip()]
        try:
            load_plugins(explicit_modules=explicit, verbose=ns.verbose)
        except PluginLoadError as exc:
            sys.stderr.write(f"{exc}\n")
            return 2

        _import_by_arg(ns.module)
        # Handle --list
        if ns.list:
            for cid, fn in sorted(CHECK_REGISTRY.items(), key=lambda kv: kv[0]):
                tags = getattr(fn, "_mrkot_tags", []) or []
                sys.stdout.write(f"{cid} {tags}\n")
            return 0

        # Tags filtering
        tagset: Optional[Set[str]] = None
        if ns.tags:
            tagset = {t.strip() for t in ns.tags.split(",") if t.strip()}

        # Run
        runner = Runner(allowed_tags=tagset, include_tags=True, verbose=ns.verbose)
        try:
            result = runner.run()
        except Runner.PlanningError as exc:
            sys.stderr.write(f"planning error: {exc}\n")
            return 2
        if ns.human:
            for r in result.items:
                sys.stdout.write(f"{r.status.value:<5} {r.id}: {r.evidence}\n")
            sys.stdout.write(f"OVERALL: {result.overall.value}\n")
        else:
            out = {
                "overall": result.overall.value,
                "counts": {k.value: v for k, v in result.counts.items()},
                "items": [
                    {"id": r.id, "status": r.status.value, "evidence": r.evidence, "tags": r.tags}
                    for r in result.items
                ],
            }
            json.dump(out, sys.stdout, ensure_ascii=False)
            sys.stdout.write("\n")
        return 0

    if ns.command == "plugins":
        if ns.list:
            eps = discover_entrypoint_plugins()
            for name, module_path in eps:
                sys.stdout.write(f"{name} {module_path}\n")
            return 0
        return 1

    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
