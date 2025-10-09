import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mr_kot import registry
from mr_kot.cli import main as mrkot_main
from mr_kot.plugins import PluginLoadError, discover_entrypoint_plugins, load_plugins

PLUGIN_TEMPLATE = """
from mr_kot import fact, check, Status

@fact
def {fact_name}():
    return "{fact_val}"

@check
def {check_name}({fact_name}):
    return Status.PASS, {fact_name}
"""


def write_module(tmp_path: Path, mod_name: str, body: str) -> str:
    pkg_dir = tmp_path / mod_name
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("\n")
    (pkg_dir / f"{mod_name}.py").write_text(body)
    # Expose as top-level module path '<name>.<name>' to avoid name clashes
    return f"{mod_name}.{mod_name}"


@pytest.fixture(autouse=True)
def clean_registries():
    # Clean registries before each test
    registry.FACT_REGISTRY.clear()
    registry.FIXTURE_REGISTRY.clear()
    registry.CHECK_REGISTRY.clear()
    yield
    registry.FACT_REGISTRY.clear()
    registry.FIXTURE_REGISTRY.clear()
    registry.CHECK_REGISTRY.clear()


def test_load_explicit_plugin_module(tmp_path, capsys):
    mod_path = write_module(
        tmp_path,
        "p1",
        PLUGIN_TEMPLATE.format(fact_name="f_one", fact_val="v1", check_name="c_one"),
    )
    sys.path.insert(0, str(tmp_path))
    try:
        load_plugins(explicit_modules=[mod_path], verbose=True)
        # ensure items registered
        assert "f_one" in registry.FACT_REGISTRY
        assert "c_one" in registry.CHECK_REGISTRY
        # ensure CLI runs
        rc = mrkot_main(["run", "mr_kot.__init__", "--human"])  # run nothing real, just to execute runner safely
        assert rc == 0
    finally:
        sys.path.remove(str(tmp_path))


def _fake_entry_points(entries):
    # entries: list[(name, module_path)]
    class EPs:
        def __init__(self, items):
            self._items = [SimpleNamespace(name=n, value=v) for n, v in items]

        def select(self, group):
            if group == "mr_kot.plugins":
                return list(self._items)
            return []

        def get(self, group, default):  # fallback API
            if group == "mr_kot.plugins":
                return list(self._items)
            return default

    return EPs(entries)


@pytest.mark.parametrize("order", [[("alpha", "pa.pa"), ("beta", "pb.pb")]])
def test_entry_points_discovery_and_load(tmp_path, monkeypatch, capsys, order):
    # Two plugins via entry points
    write_module(tmp_path, "pa", PLUGIN_TEMPLATE.format(fact_name="fa", fact_val="A", check_name="ca"))
    write_module(tmp_path, "pb", PLUGIN_TEMPLATE.format(fact_name="fb", fact_val="B", check_name="cb"))
    sys.path.insert(0, str(tmp_path))
    try:
        monkeypatch.setattr(
            "importlib.metadata.entry_points",
            lambda: _fake_entry_points(order),
        )
        eps = discover_entrypoint_plugins()
        assert eps == sorted(order, key=lambda kv: kv[0])
        load_plugins(verbose=True)
        # both loaded
        assert set(registry.FACT_REGISTRY.keys()) == {"fa", "fb"}
        assert set(registry.CHECK_REGISTRY.keys()) == {"ca", "cb"}
    finally:
        sys.path.remove(str(tmp_path))


def test_duplicate_imports_ignored(tmp_path, monkeypatch):
    mod = write_module(tmp_path, "pc", PLUGIN_TEMPLATE.format(fact_name="fx", fact_val="X", check_name="cx"))
    sys.path.insert(0, str(tmp_path))
    try:
        # Provide same module via CLI and entry points
        monkeypatch.setattr(
            "importlib.metadata.entry_points",
            lambda: _fake_entry_points([("dup", mod)]),
        )
        load_plugins(explicit_modules=[mod], verbose=True)
        # Should register only once
        assert set(registry.FACT_REGISTRY.keys()) == {"fx"}
        assert set(registry.CHECK_REGISTRY.keys()) == {"cx"}
    finally:
        sys.path.remove(str(tmp_path))


def test_id_collision_fails(tmp_path):
    # Two different modules register the same check id
    m1 = write_module(tmp_path, "pcol1", PLUGIN_TEMPLATE.format(fact_name="f1", fact_val="1", check_name="same"))
    m2 = write_module(tmp_path, "pcol2", PLUGIN_TEMPLATE.format(fact_name="f2", fact_val="2", check_name="same"))
    sys.path.insert(0, str(tmp_path))
    try:
        load_plugins(explicit_modules=[m1], verbose=False)
        with pytest.raises(ValueError) as ei:
            load_plugins(explicit_modules=[m2], verbose=False)
        msg = str(ei.value)
        assert "Duplicate check id 'same'" in msg
        assert "pcol1" in msg or "pcol2" in msg
    finally:
        sys.path.remove(str(tmp_path))


def test_plugin_import_error_aborts(tmp_path):
    bad_body = "raise RuntimeError('boom')\n"
    bad = write_module(tmp_path, "pbad", bad_body)
    sys.path.insert(0, str(tmp_path))
    try:
        with pytest.raises(PluginLoadError) as ei:
            load_plugins(explicit_modules=[bad], verbose=False)
        assert "failed to import plugin module" in str(ei.value)
        assert "boom" in str(ei.value)
    finally:
        sys.path.remove(str(tmp_path))


def test_plugins_list_command(tmp_path, monkeypatch, capsys):
    ent = [("alpha", "pa.pa"), ("beta", "pb.pb")]
    monkeypatch.setattr("importlib.metadata.entry_points", lambda: _fake_entry_points(ent))
    rc = mrkot_main(["plugins", "--list"])
    assert rc == 0
