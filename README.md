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
Facts are providers of state. They are registered with `@fact`.  
Facts may depend on other facts via function parameters, and are memoized per run.

Example:
```python
@fact
def os_release():
    return {"id": "ubuntu", "version": "22.04"}
```

### Checks
Checks verify invariants. They are registered with `@check`.  
A check may specify a `selector` argument to control whether it runs, based on facts.  
It must return a tuple `(status, evidence)` where `status` is a `Status` enum: `PASS`, `FAIL`, `WARN`, `SKIP`, or `ERROR`.

Example:
```python
from mr_kot import check, Status

@check(selector=lambda os_release: os_release["id"] == "ubuntu")
def os_is_ubuntu(os_release):
    return (Status.PASS, f"os={os_release['id']}")
```

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
