# Mr. Kot

Mr. Kot is a **pytest-inspired invariant checker**. It is designed to describe and verify **system invariants**: conditions that must hold for a system to remain functional.

Mr. Kot is specialized for **health checks**. It provides:
- **Facts**: small functions that describe system state.
- **Checks**: functions that use facts (and optionally fixtures) to verify invariants.
- **Selectors**: conditions based on facts that decide whether a check should run.
- **Fixtures**: reusable resources injected into checks with setup/teardown support.
- **Parametrization**: run the same check with multiple values or fact-provided inputs.
- **Runner**: an engine that resolves facts, applies selectors, expands parametrization, runs checks, and produces machine-readable results.

---

## Concepts

### Facts
Facts provide info that can be used by checks and other facts.
They are registered with `@fact`.
Facts may depend on other facts via function parameters, and are memoized per run.

Example:
```python
@fact
def os_release():
    return {"id": "ubuntu", "version": "22.04"}

# fact name in the function parameters means dependency on it
@fact
def os_is_ubuntu(os_release: dict) -> bool:
    return os_release["id"] == "ubuntu"
```

### Checks
Checks verify invariants. They are registered with `@check`.
It must return a tuple `(status, evidence)` where `status` is a `Status` enum: `PASS`, `FAIL`, `WARN`, `SKIP`, or `ERROR`.


You can use fact values inside a check to make a decision and craft evidence:

```python
from mr_kot import check, Status, fact

@fact
def cpu_count() -> int:
    import os
    return os.cpu_count() or 1

@check
def has_enough_cpus(cpu_count: int):
    required = 4
    if cpu_count >= required:
        return (Status.PASS, f"cpus={cpu_count} (>= {required})")
    return (Status.FAIL, f"cpus={cpu_count} (< {required})")
```

### Selectors
Selectors are optional value-based predicates evaluated before running a check instance. Dependencies come from function arguments; selectors gate execution based on fact values.

- If `selector=None` (default), the check runs unconditionally after parametrization.
- A selector must be a callable that takes fact values as parameters and returns truthy/falsy.
- Only facts are allowed in selector parameters (fixtures are not allowed).
- Facts used solely as check arguments (not in the selector) are produced during execution; if they fail, that instance becomes `ERROR` and the run continues.

Helper predicates (for common boolean checks):

```python
from mr_kot import check, Status, ALL, ANY, NOT

# Run only if both boolean facts are truthy
@check(selector=ALL("has_systemd", "has_network"))
def service_reachable(unit: str):
    return (Status.PASS, f"unit={unit}")

# Run if any of the flags is truthy
@check(selector=ANY("has_systemd", "has_sysvinit"))
def service_manager_present():
    return (Status.PASS, "present")

# Negate another predicate
@check(selector=NOT(ALL("maintenance_mode")))
def system_not_in_maintenance():
    return (Status.PASS, "ok")
```

#### Advanced selectors (predicate)
Use a predicate when you need to inspect values. Predicates are evaluated with facts only (fixtures are not allowed) and must return a boolean.

```python
from mr_kot import check

from mr_kot import check, Status

@check(selector=lambda os_release: os_release["id"] == "ubuntu")
def ubuntu_version_is_supported(os_release):
    """Pass if Ubuntu version is >= 20.04, else fail.

    Selector fail-fast guarantees os_release exists and was produced without error.
    """
    def _parse(v: str) -> tuple[int, int]:
        parts = (v.split(".") + ["0", "0"])[:2]
        try:
            return int(parts[0]), int(parts[1])
        except Exception:
            return (0, 0)

    min_major, min_minor = (20, 4)
    major, minor = _parse(os_release.get("version", "0.0"))  # type: ignore[call-arg]
    if (major, minor) >= (min_major, min_minor):
        return (Status.PASS, f"ubuntu {major}.{minor} >= {min_major}.{min_minor}")
    return (Status.FAIL, f"ubuntu {major}.{minor} < {min_major}.{min_minor}")
```

Notes:
- Selectors are evaluated per-instance after parametrization expansion.
- If a selector evaluates to False for an instance, the runner emits a `SKIP` item with evidence `selector=false`.
- Unknown fact name in a selector (or helper) → planning error, run aborts.
- Fact production error during selector evaluation → planning error, run aborts.
- Facts used only as check arguments are produced at execution; failures mark that instance `ERROR` and the run continues.

### Fixtures
Fixtures are reusable resources. They are registered with `@fixture`.
They can return a value directly, or yield a value and perform teardown afterward.
For now, fixtures are per-check: each check call receives a fresh instance.

Example:
```python
@fixture
def tmp_path():
    import tempfile, shutil
    path = tempfile.mkdtemp()
    try:
        yield path
    finally:
        shutil.rmtree(path)

@check
def can_write_tmp(tmp_path):
    import os
    test_file = os.path.join(tmp_path, "test")
    with open(test_file, "w") as f:
        f.write("ok")
    return (Status.PASS, f"wrote to {test_file}")
```

### Parametrization
Checks can be expanded into multiple instances with different arguments using `@parametrize`.

Inline values:
```python
@parametrize("mount", values=["/data", "/logs"])
@check
def mount_present(mount):
    import os
    if os.path.exists(mount):
        return (Status.PASS, f"{mount} present")
    return (Status.FAIL, f"{mount} missing")
```

Values from a fact:
```python
@fact
def systemd_units():
    return ["cron.service", "sshd.service"]

@parametrize("unit", source="systemd_units")
@check
def unit_active(unit):
    return (Status.PASS, f"{unit} is active")
```

### Runner
The runner discovers all facts, fixtures, and checks, evaluates selectors, expands parametrization, resolves dependencies, executes checks, and collects results.

Output structure:
```json
{
  "overall": "PASS",
  "counts": {"PASS": 2, "FAIL": 1, "WARN": 0, "SKIP": 0, "ERROR": 0},
  "items": [
    {"id": "os_is_ubuntu", "status": "PASS", "evidence": "os=ubuntu"},
    {"id": "mount_present[/data]", "status": "PASS", "evidence": "/data present"},
    {"id": "mount_present[/logs]", "status": "FAIL", "evidence": "/logs missing"}
  ]
}
```

The `overall` field is computed by severity ordering: `ERROR > FAIL > WARN > PASS`.

---
