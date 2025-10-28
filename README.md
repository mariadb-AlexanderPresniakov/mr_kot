# Mr. Kot

Mr. Kot is a **pytest-inspired invariant checker**. It is designed to describe and verify **system invariants** — conditions that must hold for a system to remain functional.

The central concept in Mr. Kot is a **check**: a function that validates a condition (for example, file presence, permissions, or a config section) and returns a status — one of `PASS`, `WARN`, `FAIL`, or `ERROR` — plus evidence (a string containing description). In pytest terms, checks are tests.

You can have many checks, but not all of them need to run in every environment. For example, you don’t want to run systemd‑specific checks when the app runs in a container. To control this, you attach a **selector** to a check that specifies the conditions under which it should run. In pytest terms, selectors are similar to skipif markers.

In selectors we use one more important concept of Mr. Kot - **facts**. Facts are functions that return some value (e.g., OS release, CPU count). Selectors can use these values (e.g., “run this check only if the `distro` fact is (returns) Ubuntu,” “run only if `has_systemd` is (returns) true”). Facts are evaluated once per run.

Checks can also depend on facts to get values needed for their logic without recomputing them (cleanly separating “what data we need to perform the check” from “how we perform the check”). The pytest analogy is a fixture or, more generally, dependency injection: add the fact name to the check function’s parameter list and its value will be provided.

In many cases, it’s cleaner to write check logic for a single entity (e.g., validating permissions of one directory) and use **parametrization** to run it multiple times with different values. This produces precise diagnostics for the specific item that failed. You can pass a literal list of values or reference a fact that provides them. For example, data directory paths may depend on the distribution, so you can create a `data_dirs` fact that returns a list of paths and pass it to `parametrize`.

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
Checks must return a tuple `(status, evidence)` where `status` is a `Status` enum: `PASS`, `FAIL`, `WARN`, `SKIP`, or `ERROR` (returned automatically if the check caused an unhandled exception).

You can use fact values inside a check to make a decision and craft evidence:

```python
import os
from mr_kot import check, Status, fact

@fact
def cpu_count() -> int:
    return os.cpu_count() or 1

@check
def has_enough_cpus(cpu_count: int):
    required = 4
    if cpu_count >= required:
        return (Status.PASS, f"cpus={cpu_count} (>= {required})")
    return (Status.FAIL, f"cpus={cpu_count} (< {required})")
```

If you want a fact or fixture for its side effect (e.g. you don't need its value inside the function), use `@depends` instead of adding it as a function parameter.

```python
from mr_kot import check, depends, fixture, Status

@fixture
def side_effectful_fixture():
    mount("/data")
    yield True # No useful value, just side effect
    umount("/data")

@check
@depends("side_effectful_fixture") # the check needs only the side effect of the fixture (dir must be mounted)
def fs_write_smoke():
    with open("/data/test", "w") as f:
        f.write("ok")
        return (Status.PASS, "ok")
```

### Selectors
Selectors decide whether a check instance should run, based on fact values.
They are passed as a parameter of @check(selector=...).
If selector is not passed, the check runs unconditionally after parametrization.

There are two forms of the selectors:

- **String shorthand (recommended for common cases):** a comma-separated list of fact names. All listed facts must exist and evaluate truthy for the check to run.
  This is equivalent to `ALL(<fact_name>, <fact_name>, ...)`.
- **Predicate callable (advanced):** a function taking facts as arguments and returning a boolean.
  There are helper predicates available: `ALL`, `ANY`, `NOT`.

- Only facts are allowed in selectors; fixtures are not allowed.
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
- Fixtures are not allowed in selectors.
- Facts used only as check arguments are produced at execution; failures mark that instance `ERROR` and the run continues.

### Parametrization
Checks can be expanded into multiple instances with different arguments using `@parametrize`.

Inline values:
```python
@check
@parametrize("mount", values=["/data", "/logs"])
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

@check
@parametrize("unit", source="systemd_units")
def unit_active(unit):
    return (Status.PASS, f"{unit} is active")
```

Use `fail_fast=True` in `@parametrize` to stop executing remaining instances of the same check after the first `FAIL` or `ERROR`:

```python
@check
@parametrize("mount", values=["/data", "/data/logs"], fail_fast=True)
def mount_present(mount):
    import os
    return (Status.PASS, f"{mount} present") if os.path.exists(mount) else (Status.FAIL, f"{mount} missing")
```

When fail-fast triggers, remaining instances are emitted as `SKIP`.

### Validators and `check_all()`

Validators are small reusable building blocks of logic used inside checks. They represent ready‑made validation routines for specific domains (for example, files, directories, services, or network resources). Each validator can be configured with parameters (like expected mode, owner, or recursion) and then applied to a specific target. Validators return the same result format as a check — a status and evidence — so they can be freely combined.

You can run several validators together over one target with `check_all()`, which executes them in order and aggregates their results, stopping early if one fails (or running all if configured). This lets you compose complex checks from small, prepared, domain‑specific pieces of logic without writing everything manually.

Details:
- A validator is `validator(target) -> (Status|str, str)` (status, evidence).
- Build validators as plain functions or callable classes that capture options in `__init__` and implement `__call__(target)`.
- `check_all(target, *validators, fail_fast=True)` runs validators in order.
  - `fail_fast=True`: stop at the first `FAIL` or `ERROR` and return that evidence.
  - `fail_fast=False`: run all, aggregate by severity (`ERROR > FAIL > WARN > PASS`), join messages with `"; "`; if all pass, evidence is `target=<repr> ok`.
- Robustness: unexpected exceptions in validators are converted to `ERROR` with evidence `validator=<name> error=<ExcType>: <message>`.

Example:

```python
from mr_kot import check, Status, check_all

class HasPrefix:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def __call__(self, target: str):
        if target.startswith(self.prefix):
            return (Status.PASS, f"{target} has {self.prefix}")
        return (Status.FAIL, f"{target} missing {self.prefix}")

def non_empty(t: str):
    return (Status.PASS, "non-empty") if t else (Status.FAIL, "empty")

@check
def demo():
    status, evidence = check_all("abc123", non_empty, HasPrefix("abc"), fail_fast=True)
    return (status, evidence)
```

You can OR-combine validators with `any_of(v1, v2, ...)`:

```python
from mr_kot.validators import any_of

# Passes if owner is either mysql or mariadb; on failure aggregates both diagnostics
status, evidence = check_all(
    path,
    any_of(OwnerIs('mysql'), OwnerIs('mariadb')),
)
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

### Plugins

Mr. Kot can discover and load external plugins that register facts, fixtures, and checks at import time.

- **Discovery sources**
  - Entry points: installed distributions that declare the entry-point group `mr_kot.plugins` are discovered and imported.
  - Explicit list: pass modules via the CLI `--plugins pkg1,pkg2` to import them first, in order.

- **Order and dedup**
  - CLI `--plugins` are imported first (left to right), then entry-point plugins sorted by their entry-point name.
  - If the same module appears in both, it is imported only once.

- **Uniqueness rule**
  - IDs (function names) must be unique across all loaded plugins and the current module; collisions abort the run.

