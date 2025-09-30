# Mr. Kot

Mr. Kot is a **pytest-inspired invariant checker**. It is designed to describe and verify **system invariants**: conditions that must hold for a system to remain functional.

Mr. Kot is specialized for **health checks**. It provides:
- **Facts**: small functions that describe system state.
- **Checks**: functions that use facts to verify invariants.
- **Runner**: an engine that resolves facts, runs checks, and produces machine-readable results.

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
A check must return a tuple `(status, evidence)` where `status` is a `Status` enum: `Status.PASS`, `Status.FAIL`, `Status.WARN`, `Status.SKIP`, or `Status.ERROR`.

Example:
```python
from mr_kot import check, Status

@check
def os_is_ubuntu(os_release):
    return (Status.PASS, f"os={os_release['id']}")
```

### Runner
The runner discovers all facts and checks, builds a dependency graph, resolves facts, executes checks, and collects results.

Output structure:
```json
{
  "overall": "PASS",
  "counts": {"PASS": 1, "FAIL": 0, "WARN": 0, "SKIP": 0, "ERROR": 0},
  "items": [
    {"id": "os_is_ubuntu", "status": "PASS", "evidence": "os=ubuntu"}
  ]
}
```

The `overall` field is computed by severity ordering: `FAIL > WARN > PASS`.

---
