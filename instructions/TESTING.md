# Foreman — Testing Reference

This document is the **canonical reference for test conventions**. Read it before adding any new test file or test case.

---

## Test Philosophy

- **No real database.** Every test uses in-memory `dict` stores and `monkeypatch` to replace CRUD functions. The actual asyncpg connection is never exercised.
- **Isolated.** Every test function gets a fresh state via `autouse` fixture teardown (`dict.clear()` + `app.dependency_overrides.clear()`).
- **Fast.** No I/O, no network. The full suite should complete in a few seconds.

---

## File Layout

```
tests/
├── __init__.py
├── test_db.py          ← Database helper unit tests
├── test_main.py        ← Root/health endpoint smoke tests
├── test_projects.py    ← Project resource endpoint tests (reference file)
├── test_telemetry.py   ← OpenTelemetry instrumentation tests
└── test_users.py       ← User resource endpoint tests
```

One file per resource or application concern. Name it `test_<resource>.py`.

---

## Import Order

Follow PEP 8 / isort conventions — three groups, separated by blank lines:

```python
# Stdlib
import uuid
from datetime import datetime, timezone

# Third-party
import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

# Local
from foreman.api.deps import get_current_user, get_db
from foreman.main import app
from foreman.models.project import Project
```

---

## Section Dividers

Use comment dividers to separate logical blocks within a file:

```python
# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
```

---

## Fixtures

### `autouse` setup/teardown fixture

Every endpoint test file **must** have an `autouse=True` fixture called `mock_dependencies` that:

1. Seeds any required in-memory data (fixed UUIDs for multi-user tests).
2. Defines and registers `override_get_db` (returns `None`) and `override_get_current_user` (reads `X-User-ID` header from in-memory store).
3. Defines async mock functions for each CRUD operation and patches them via `monkeypatch.setattr` using the **fully qualified attribute path** seen by the endpoint module:
   ```python
   monkeypatch.setattr("foreman.api.v1.endpoints.projects.crud.create_project", mock_create_project)
   ```
4. `yield`s, then clears all stores and `app.dependency_overrides` in teardown:
   ```python
   yield
   users_db.clear()
   projects_db.clear()
   app.dependency_overrides.clear()
   ```

### `client` fixture

```python
@pytest.fixture
def client():
    """TestClient for the FastAPI app."""
    return TestClient(app)
```

### Auth header fixtures (multi-user tests)

Pre-define fixed user UUIDs at module level and expose them as fixtures:

```python
USER_A_ID = uuid.uuid4()
USER_B_ID = uuid.uuid4()

@pytest.fixture
def headers_a():
    """Auth headers for User A."""
    return {"X-User-ID": str(USER_A_ID)}

@pytest.fixture
def headers_b():
    """Auth headers for User B."""
    return {"X-User-ID": str(USER_B_ID)}
```

---

## Arrange / Act / Assert (AAA)

Every test function body **must** have `# Arrange`, `# Act`, and `# Assert` section comments, in that order.

**Rules:**
- If Arrange needs no code (no external state to set up), add a brief inline note: `# Arrange — no setup required`.
- If Act and Assert are inseparable (e.g., `pytest.raises`), collapse them: `# Act / Assert`.
- Never put assertions inside the Act block or test logic inside the Assert block.
- Keep each test focused on **one behaviour**. Do not chain multiple independent scenarios into a single function.
- If there are tests that are very similar, consider combining them into a single test function with multiple assertions.

---

## Docstrings

Every test function **must** have a one-line docstring describing the scenario and expected outcome:

```python
def test_get_project_not_found(client, headers_a):
    """GET /v1/projects/{id} with an unknown ID should return 404."""
```

Pattern: `[<HTTP method>|<method name>] <path> [+ condition] should <expected result>.`

---

## Helper Functions

For repetitive setup (e.g., creating a resource before testing it), extract a module-level helper:

```python
def create_project(client, headers, name="Test Project", image_url=None):
    """Create a project via the API and assert success."""
    body = {"name": name}
    if image_url:
        body["original_image_url"] = image_url
    resp = client.post("/v1/projects/", headers=headers, json=body)
    assert resp.status_code == 201
    return resp.json()
```

---

## Mandatory Test Cases Per Resource

Every new resource endpoint file must cover:

| # | Scenario | Expected |
|---|----------|----------|
| 1 | List — empty store | `200 []` |
| 2 | List — after creates | `200` with correct count |
| 3 | Create — valid payload | `201`, correct fields |
| 4 | Create — missing required field | `422` |
| 5 | Get by ID — found | `200`, correct data |
| 6 | Get by ID — not found | `404` |
| 7 | Update — partial update | `200`, untouched fields preserved |
| 8 | Update — not found | `404` |
| 9 | Update — extra/unknown fields | `422` |
| 10 | Delete — success | `204`, subsequent GET → `404` |
| 11 | Delete — not found | `404` |
| 12 | Ownership — another user's resource | `404` on GET, PATCH, DELETE |
| 13 | Unauthenticated — missing header | `401` |

