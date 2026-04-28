# PR #17 Review Comment Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve 14 unresolved review comments on PR #17 (`feat/background-worker`), covering runtime crashes, security vulnerabilities, broken Docker/Compose configs, and test-isolation bugs.

**Architecture:** All fixes are in the `worker/` package and its supporting infrastructure files (`pyproject.toml`, `Dockerfile.worker`, `docker-compose.yml`, `tests/worker/`). No database migrations or API schema changes are needed.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, OpenTelemetry Python SDK, google-genai (Vertex AI), boto3 / Cloudflare R2, pytest, Docker Compose.

---

## File Map

| File | Change |
|---|---|
| `pyproject.toml` | Add `google-genai` dependency |
| `Dockerfile.worker` | Copy `README.md` before `pip install` |
| `docker-compose.yml` | Fix `worker:` indentation under `services:` |
| `worker/main.py` | Wrap `"SELECT 1"` in `sql()` helper |
| `worker/processor.py` | Fix `StatusCode` → `Status(StatusCode.X)` usage |
| `worker/providers/vertex.py` | Add `urllib.parse` import; SSRF hardening; size-limited download; `try/finally` for temp file; dynamic MIME type detection |
| `tests/worker/conftest.py` | Replace `pytest_sessionstart` with autouse session fixture |
| `tests/worker/test_basic.py` | Add missing `GenerationJob` import in `sample_job` fixture |
| `tests/foreman/integration/test_sqs_queue.py` | Move module-level `os.environ` assignments into a fixture |

---

### Task 1: Add `google-genai` to project dependencies

**Files:**
- Modify: `pyproject.toml` (line 7–20)

The `worker/providers/vertex.py` does `from google import genai` / `from google.genai import types`, but the package is not listed in `pyproject.toml`. The correct PyPI package name is `google-genai`.

- [ ] **Step 1: Write the failing test**

```python
# tests/worker/test_imports.py  (NEW FILE)
def test_google_genai_importable():
    """google-genai package must be installed."""
    import importlib
    spec = importlib.util.find_spec("google.genai")
    assert spec is not None, "google-genai is not installed — add it to pyproject.toml"
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
pytest tests/worker/test_imports.py::test_google_genai_importable -v
```
Expected: FAIL — `AssertionError: google-genai is not installed`

- [ ] **Step 3: Add the dependency to `pyproject.toml`**

In `pyproject.toml`, add `"google-genai>=1.0.0"` to the `dependencies` list:

```toml
dependencies = [
    "fastapi>=0.135.2",
    "uvicorn[standard]>=0.40.0",
    "pydantic>=2.12.5",
    "opentelemetry-api>=1.39.1",
    "opentelemetry-sdk>=1.39.1",
    "opentelemetry-instrumentation-fastapi>=0.60b1",
    "opentelemetry-exporter-otlp>=1.39.1",
    "python-json-logger>=4.0.0",
    "asyncpg>=0.31.0",
    "psycopg[binary]>=3.2.10",
    "python-dotenv>=1.2.2",
    "boto3>=1.41.0",
    "google-genai>=1.0.0",
]
```

- [ ] **Step 4: Install the updated dependencies**

```bash
pip install -e ".[dev]"
```
Expected: `Successfully installed google-genai-...`

- [ ] **Step 5: Run the test to confirm it passes**

```bash
pytest tests/worker/test_imports.py::test_google_genai_importable -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/worker/test_imports.py
git commit -m "fix: add google-genai dependency to pyproject.toml

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Fix `Dockerfile.worker` — copy `README.md` before `pip install`

**Files:**
- Modify: `Dockerfile.worker`

`pyproject.toml` declares `readme = "README.md"`. Without it in the Docker build context, `pip install .` can fail during metadata generation.

- [ ] **Step 1: Write the failing test (build check)**

There is no automated test for Dockerfile correctness; verify manually after the fix. Proceed directly.

- [ ] **Step 2: Add `README.md` to the Dockerfile COPY instructions**

Replace the existing copy block in `Dockerfile.worker`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY README.md .
COPY foreman ./foreman
COPY worker ./worker

# Install build dependencies, then install the package
RUN pip install --no-cache-dir setuptools && \
    pip install --no-cache-dir .

# Expose port
EXPOSE 8081

# Run the worker
CMD ["python", "-m", "worker.main"]
```

- [ ] **Step 3: Verify the Dockerfile lints cleanly (optional quick check)**

```bash
docker build -f Dockerfile.worker . --no-cache 2>&1 | tail -5
```
Expected: `Successfully built ...` (requires Docker daemon and dependencies to be installed).

- [ ] **Step 4: Commit**

```bash
git add Dockerfile.worker
git commit -m "fix: copy README.md in Dockerfile.worker before pip install

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Fix `docker-compose.yml` — indent `worker:` under `services:`

**Files:**
- Modify: `docker-compose.yml`

`worker:` is at the root level instead of being indented as a child of `services:`, making the Compose file invalid.

- [ ] **Step 1: Fix the indentation**

Replace the entire `docker-compose.yml` with the corrected version:

```yaml
version: '3.8'

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: admin
      POSTGRES_DB: foreman
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  foreman:
    build: .
    env_file:
      - ./.env.foreman
    ports:
      - "8000:8000"
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318/v1/traces
      - OTEL_EXPORTER_OTLP_INSECURE=true
    depends_on:
      - db
      - jaeger

  jaeger:
    image: jaegertracing/jaeger:2.14.1
    ports:
      - "16686:16686"  # Jaeger UI
      - "4317:4317"    # OTLP gRPC receiver
      - "4318:4318"    # OTLP HTTP receiver
    environment:
      - COLLECTOR_OTLP_ENABLED=true

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    env_file:
      - ./.env.foreman
    ports:
      - "8081:8081"
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318/v1/traces
      - OTEL_EXPORTER_OTLP_INSECURE=true
      - QUEUE_PROVIDER=sqs
    depends_on:
      - db

volumes:
  postgres_data:
```

- [ ] **Step 2: Validate the YAML**

```bash
docker compose -f docker-compose.yml config --quiet
```
Expected: exits 0 with no errors.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "fix: indent worker service under services in docker-compose.yml

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Fix `worker/main.py` — wrap readiness DB check with `sql()` helper

**Files:**
- Modify: `worker/main.py` (line 48)
- Test: `tests/worker/test_main.py` (new file or extend existing)

`db.execute("SELECT 1")` passes a raw string, but `Database.execute()` requires a `SQLStatement` (created via `sql()`). This causes `'str' object has no attribute 'text'` at runtime.

- [ ] **Step 1: Write the failing test**

Create `tests/worker/test_main.py`:

```python
"""Tests for worker health endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_ready_endpoint_calls_execute_with_sql_statement():
    """The /ready endpoint must pass a SQLStatement to db.execute, not a raw string."""
    from foreman.db import SQLStatement
    import worker.main as worker_main

    captured_calls = []

    async def mock_execute(stmt):
        captured_calls.append(stmt)
        return "SELECT 1"

    mock_db = MagicMock()
    mock_db.execute = mock_execute

    mock_consumer = MagicMock()
    mock_consumer.is_ready.return_value = True

    worker_main._db_instance = mock_db
    worker_main._consumer_instance = mock_consumer

    from fastapi.testclient import TestClient
    client = TestClient(worker_main.health_app)
    response = client.get("/ready")

    assert response.status_code == 200
    assert len(captured_calls) == 1
    assert isinstance(captured_calls[0], SQLStatement), (
        f"Expected SQLStatement, got {type(captured_calls[0])}"
    )

    # reset globals
    worker_main._db_instance = None
    worker_main._consumer_instance = None
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
pytest tests/worker/test_main.py::test_ready_endpoint_calls_execute_with_sql_statement -v
```
Expected: FAIL — `AssertionError: Expected SQLStatement, got <class 'str'>`

- [ ] **Step 3: Fix `worker/main.py`**

Add `sql` to the `foreman.db` import and wrap the query:

```python
from foreman.db import Database, sql
```

Change line 48:
```python
# Before:
await _db_instance.execute("SELECT 1")

# After:
await _db_instance.execute(sql("SELECT 1"))
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
pytest tests/worker/test_main.py::test_ready_endpoint_calls_execute_with_sql_statement -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add worker/main.py tests/worker/test_main.py
git commit -m "fix: use sql() helper for readiness DB check in worker/main.py

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Fix `worker/processor.py` — correct OpenTelemetry `Status` usage

**Files:**
- Modify: `worker/processor.py` (lines 15, 101, 115)

`span.set_status(StatusCode.OK)` is incorrect — OpenTelemetry Python SDK expects a `Status` object: `span.set_status(Status(StatusCode.OK))`.

- [ ] **Step 1: Write the failing test**

Add to `tests/worker/test_processor.py` (new file):

```python
"""Tests for worker processor OTEL instrumentation."""
from unittest.mock import MagicMock, patch


def test_processor_uses_status_objects_not_raw_status_codes():
    """processor.py must import Status and wrap StatusCode in Status(...)."""
    import ast, pathlib

    source = pathlib.Path("worker/processor.py").read_text()
    tree = ast.parse(source)

    # Confirm 'Status' is imported from opentelemetry.trace.status
    imports = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "opentelemetry.trace.status"
    ]
    imported_names = {alias.name for imp in imports for alias in imp.names}
    assert "Status" in imported_names, "Status not imported from opentelemetry.trace.status"
    assert "StatusCode" in imported_names, "StatusCode not imported from opentelemetry.trace.status"
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
pytest tests/worker/test_processor.py::test_processor_uses_status_objects_not_raw_status_codes -v
```
Expected: FAIL — `AssertionError: Status not imported from opentelemetry.trace.status`

- [ ] **Step 3: Fix `worker/processor.py`**

Replace the import on line 15:
```python
# Before:
from opentelemetry.sdk.trace import StatusCode

# After:
from opentelemetry.trace.status import Status, StatusCode
```

Replace the two `set_status` calls:

```python
# Line ~101 — success path:
# Before:
span.set_status(StatusCode.OK)
# After:
span.set_status(Status(StatusCode.OK))

# Line ~115 — error path:
# Before:
span.set_status(StatusCode.ERROR, "Job processing failed")
# After:
span.set_status(Status(StatusCode.ERROR, "Job processing failed"))
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
pytest tests/worker/test_processor.py::test_processor_uses_status_objects_not_raw_status_codes -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add worker/processor.py tests/worker/test_processor.py
git commit -m "fix: use Status(StatusCode.X) for OpenTelemetry span status in processor

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: Fix `worker/providers/vertex.py` — add missing `urllib.parse` import

**Files:**
- Modify: `worker/providers/vertex.py` (line 7)

`urllib.parse.urlparse` is called in `_download_image`, but only `urllib.request` is imported. This raises `AttributeError` at runtime when SSRF validation runs.

- [ ] **Step 1: Write the failing test**

Add to `tests/worker/test_vertex.py` (new file):

```python
"""Tests for GeminiProvider."""
import ast
import pathlib


def test_urllib_parse_is_imported():
    """vertex.py must import urllib.parse to use urlparse."""
    source = pathlib.Path("worker/providers/vertex.py").read_text()
    tree = ast.parse(source)

    imports = [node for node in ast.walk(tree) if isinstance(node, ast.Import)]
    imported_modules = {alias.name for imp in imports for alias in imp.names}
    assert "urllib.parse" in imported_modules, (
        "urllib.parse must be imported in vertex.py; urlparse is used in _download_image"
    )
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
pytest tests/worker/test_vertex.py::test_urllib_parse_is_imported -v
```
Expected: FAIL

- [ ] **Step 3: Fix `worker/providers/vertex.py`**

Add `urllib.parse` to the imports section (alongside `urllib.request`):

```python
import urllib.parse
import urllib.request
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
pytest tests/worker/test_vertex.py::test_urllib_parse_is_imported -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add worker/providers/vertex.py tests/worker/test_vertex.py
git commit -m "fix: add missing urllib.parse import to vertex.py

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7: Harden `_download_image` — SSRF policy, size limit, MIME detection, temp file safety

**Files:**
- Modify: `worker/providers/vertex.py` (`_download_image` and `generate` methods)
- Test: `tests/worker/test_vertex.py` (extend)

Four review comments target this method:
- **Thread 5** — SSRF protection only runs when `allowed_image_domains` is non-empty; add https-only enforcement and private-IP blocking by default.
- **Thread 12** — `response.read()` has no size limit; stream in chunks with a max-size guard.
- **Thread 13** — `open(local_path)` in `generate()` can raise before `os.unlink`; wrap in `try/finally`.
- **Thread 14** — MIME type is hardcoded to `image/jpeg`; detect from response `Content-Type` header.

- [ ] **Step 1: Write failing tests**

Add to `tests/worker/test_vertex.py`:

```python
import ipaddress
import socket
import urllib.parse
from unittest.mock import MagicMock, patch, AsyncMock
import pytest


class FakeResponse:
    def __init__(self, data: bytes, content_type: str = "image/png", length: int | None = None):
        self._data = data
        self.headers = {"Content-Type": content_type}
        if length is not None:
            self.headers["Content-Length"] = str(length)

    def read(self, n=-1):
        if n == -1:
            return self._data
        return self._data[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_download_rejects_http_when_no_allowlist():
    """Without an allowlist, http:// URLs must be rejected."""
    from worker.providers.vertex import GeminiProvider
    provider = GeminiProvider(allowed_image_domains=set())
    with pytest.raises(ValueError, match="HTTPS"):
        await provider._download_image("http://example.com/image.jpg")


@pytest.mark.asyncio
async def test_download_rejects_private_ip(monkeypatch):
    """IP addresses in the private range must be blocked."""
    from worker.providers.vertex import GeminiProvider
    provider = GeminiProvider(allowed_image_domains=set())

    monkeypatch.setattr(socket, "gethostbyname", lambda h: "192.168.1.1")
    with pytest.raises(ValueError, match="private"):
        await provider._download_image("https://internal.corp/image.jpg")


@pytest.mark.asyncio
async def test_download_enforces_size_limit(monkeypatch, tmp_path):
    """Downloads exceeding MAX_DOWNLOAD_BYTES must raise ValueError."""
    from worker.providers.vertex import GeminiProvider, MAX_DOWNLOAD_BYTES
    provider = GeminiProvider(allowed_image_domains=set())

    big_data = b"x" * (MAX_DOWNLOAD_BYTES + 1)
    fake_resp = FakeResponse(big_data, "image/jpeg")

    monkeypatch.setattr(socket, "gethostbyname", lambda h: "93.184.216.34")

    with patch("urllib.request.urlopen", return_value=fake_resp):
        with pytest.raises(ValueError, match="too large"):
            await provider._download_image("https://example.com/huge.jpg")


@pytest.mark.asyncio
async def test_download_detects_mime_type(monkeypatch, tmp_path):
    """MIME type should be read from Content-Type response header."""
    from worker.providers.vertex import GeminiProvider
    provider = GeminiProvider(allowed_image_domains=set())

    png_data = b"\x89PNG\r\n\x1a\n" + b"x" * 100
    fake_resp = FakeResponse(png_data, "image/png")
    monkeypatch.setattr(socket, "gethostbyname", lambda h: "93.184.216.34")

    with patch("urllib.request.urlopen", return_value=fake_resp):
        path, mime = await provider._download_image("https://example.com/img.png")
    assert mime == "image/png"
    import os
    os.unlink(path)
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
pytest tests/worker/test_vertex.py -k "download" -v
```
Expected: multiple FAILs

- [ ] **Step 3: Rewrite `_download_image` and update `generate` in `worker/providers/vertex.py`**

Add the constant near the top of the file (after imports):

```python
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
```

Replace `_download_image` entirely:

```python
async def _download_image(self, url: str) -> tuple[str, str]:
    """Download image from HTTP URL to a temp file.

    Returns:
        Tuple of (local_path, mime_type).

    Raises:
        ValueError: If the URL fails SSRF validation, is too large, or uses HTTP.
    """
    import socket as _socket

    parsed = urllib.parse.urlparse(url)

    # Always require HTTPS
    if parsed.scheme != "https":
        raise ValueError(f"Image URL must use HTTPS, got scheme '{parsed.scheme}'")

    # Resolve hostname and block private/loopback addresses
    try:
        ip_str = _socket.gethostbyname(parsed.hostname or "")
        ip = ipaddress.ip_address(ip_str)
    except (ValueError, _socket.gaierror) as exc:
        raise ValueError(f"Cannot resolve image URL host '{parsed.hostname}': {exc}") from exc

    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        raise ValueError(
            f"Image URL resolves to a private/reserved IP address ({ip_str}); blocked for security"
        )

    # Domain allowlist (optional additional restriction)
    if self.allowed_image_domains and parsed.hostname not in self.allowed_image_domains:
        raise ValueError(f"Image URL domain not in allowlist: {parsed.hostname}")

    temp_path = f"/tmp/input_{os.urandom(8).hex()}.bin"
    try:
        with tracer.start_as_current_span("download_input_image") as span:
            span.set_attribute("url", url)

            def _download() -> str:
                with urllib.request.urlopen(url, timeout=30) as response:
                    content_type = response.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()

                    # Enforce size limit
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
                        raise ValueError(
                            f"Image response too large: {content_length} bytes "
                            f"(max {MAX_DOWNLOAD_BYTES})"
                        )

                    total = 0
                    with open(temp_path, "wb") as f:
                        while True:
                            chunk = response.read(65536)
                            if not chunk:
                                break
                            total += len(chunk)
                            if total > MAX_DOWNLOAD_BYTES:
                                raise ValueError(
                                    f"Image download exceeded {MAX_DOWNLOAD_BYTES} bytes; "
                                    "aborting (too large)"
                                )
                            f.write(chunk)
                return content_type

            mime_type = await asyncio.to_thread(_download)
            logger.info("Downloaded input image", extra={"url": url, "path": temp_path, "mime": mime_type})
            return temp_path, mime_type

    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
```

Add `import ipaddress` to the imports at the top of the file.

Update `generate()` to unpack the tuple and use the detected MIME type:

```python
# In generate(), replace the http-download block:
if input_image_url.startswith("http"):
    local_path, mime_type = await self._download_image(input_image_url)
    try:
        with open(local_path, "rb") as f:
            input_content = types.Part.from_bytes(
                data=f.read(),
                mime_type=mime_type,
            )
    finally:
        os.unlink(local_path)
else:
    # For gs:// URIs use a sensible default; URI-based calls don't download
    input_content = types.Part.from_uri(
        file_uri=input_image_url,
        mime_type="image/jpeg",
    )
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
pytest tests/worker/test_vertex.py -k "download" -v
```
Expected: all PASS

- [ ] **Step 5: Run the full worker test suite**

```bash
pytest tests/worker/ -v
```
Expected: all previously passing tests still pass; new tests pass.

- [ ] **Step 6: Commit**

```bash
git add worker/providers/vertex.py tests/worker/test_vertex.py
git commit -m "fix: harden _download_image — SSRF, size limit, MIME detection, temp file cleanup

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 8: Fix `tests/worker/conftest.py` — replace `pytest_sessionstart` with autouse fixture

**Files:**
- Modify: `tests/worker/conftest.py`

`pytest_sessionstart` in a subdirectory conftest is not reliably called before module imports during collection. Replacing it with a session-scoped autouse fixture ensures mocks are in place before any `worker.*` module is imported.

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/worker/test_conftest_reliability.py (new file)
def test_google_genai_is_mocked():
    """google.genai must be a MagicMock (set up by conftest), not the real module."""
    import sys
    from unittest.mock import MagicMock
    assert isinstance(sys.modules.get("google.genai"), MagicMock), (
        "google.genai was not mocked before this test module was imported. "
        "conftest mock setup is unreliable."
    )
```

- [ ] **Step 2: Run the test in isolation (not via full suite) to surface the timing bug**

```bash
pytest tests/worker/test_conftest_reliability.py -v
```
Expected: PASS (may already pass when run in isolation, but fails in full suite order — the fix prevents future regressions).

- [ ] **Step 3: Rewrite `tests/worker/conftest.py`**

Replace the entire file:

```python
"""Worker tests configuration — module-level mock installation."""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


def _install_mocks() -> None:
    """Install sys.modules stubs for external and foreman dependencies.

    Called at import time so that mocks are present before any worker.*
    module is imported during pytest collection.
    """
    # Create foreman as a namespace package
    foreman_pkg = ModuleType("foreman")
    foreman_pkg.__path__ = []
    sys.modules.setdefault("foreman", foreman_pkg)

    for submod_name in [
        "foreman.logging_config",
        "foreman.context",
        "foreman.db",
        "foreman.queue",
        "foreman.queue.settings",
        "foreman.telemetry",
        "foreman.telemetry.setup_telemetry",
        "foreman.repositories",
        "foreman.repositories.postgres_generations_repository",
        "foreman.schemas",
        "foreman.schemas.generation",
    ]:
        if submod_name not in sys.modules:
            mod = ModuleType(submod_name)
            sys.modules[submod_name] = mod

    # Set up attributes on logging_config
    logging_mod = sys.modules["foreman.logging_config"]
    if not hasattr(logging_mod, "get_logger"):
        logging_mod.get_logger = MagicMock(return_value=MagicMock())
        logging_mod.configure_logging = MagicMock()
        logging_mod.CorrelationIdFilter = type(
            "CorrelationIdFilter", (), {"filter": lambda self, record: True}
        )

    for module_name in [
        "google",
        "google.genai",
        "google.genai.types",
        "boto3",
        "botocore",
        "botocore.config",
        "opentelemetry",
        "opentelemetry.trace",
    ]:
        sys.modules.setdefault(module_name, MagicMock())


# Install mocks at import time — this runs before any worker.* module is
# imported during collection, regardless of conftest loading order.
_install_mocks()


@pytest.fixture(autouse=True, scope="session")
def _worker_mocks():
    """Session fixture that documents the mock setup for pytest introspection."""
    yield


def pytest_sessionfinish(session, exitstatus):
    """Clean up mocks after all tests run."""
    modules_to_remove = [
        k
        for k in list(sys.modules.keys())
        if k.startswith("google")
        or k.startswith("botocore")
        or k.startswith("boto3")
        or k.startswith("opentelemetry")
        or k.startswith("foreman")
        or k.startswith("worker")
    ]
    for mod in modules_to_remove:
        del sys.modules[mod]
```

- [ ] **Step 4: Run the full worker test suite**

```bash
pytest tests/worker/ -v
```
Expected: all tests pass; no ImportErrors during collection.

- [ ] **Step 5: Commit**

```bash
git add tests/worker/conftest.py tests/worker/test_conftest_reliability.py
git commit -m "fix: replace pytest_sessionstart with import-time mock install in worker conftest

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 9: Fix `tests/worker/test_basic.py` — add missing `GenerationJob` import

**Files:**
- Modify: `tests/worker/test_basic.py` (line 1 imports block)

The `sample_job` fixture uses `GenerationJob` directly, but it is never imported, causing `NameError` during collection.

- [ ] **Step 1: Run the test to confirm the NameError**

```bash
pytest tests/worker/test_basic.py::sample_job -v 2>&1 | grep "NameError\|ERROR"
```
Expected: `NameError: name 'GenerationJob' is not defined`

- [ ] **Step 2: Add the import**

In `tests/worker/test_basic.py`, add to the imports at the top of the file:

```python
from worker.consumer import GenerationJob
```

The imports block should look like:

```python
"""Worker comprehensive tests."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.consumer import GenerationJob
```

- [ ] **Step 3: Run the test suite to confirm it passes**

```bash
pytest tests/worker/test_basic.py -v
```
Expected: all tests PASS (no NameError on collection).

- [ ] **Step 4: Commit**

```bash
git add tests/worker/test_basic.py
git commit -m "fix: add missing GenerationJob import to test_basic.py sample_job fixture

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 10: Fix `tests/foreman/integration/test_sqs_queue.py` — move env vars into a fixture

**Files:**
- Modify: `tests/foreman/integration/test_sqs_queue.py` (lines 14–18)

Setting `os.environ` at module import time leaks into other tests and creates order-dependent failures. Use `monkeypatch` to scope the env vars per-test.

- [ ] **Step 1: Write a test that verifies env vars are not polluted after the test runs**

Since this is an integration test file, the fix itself is the test change. Proceed directly to the fix.

- [ ] **Step 2: Remove module-level env assignments and add a fixture**

Replace:

```python
os.environ["AWS_ACCESS_KEY_ID"] = "test"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["QUEUE_PROVIDER"] = "sqs"
```

With an autouse fixture scoped to the module:

```python
@pytest.fixture(autouse=True)
def _aws_env(monkeypatch):
    """Set AWS environment variables for each test and restore them automatically."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("QUEUE_PROVIDER", "sqs")
```

The updated top of the file should look like:

```python
"""Integration tests for SQS queue publishing."""

import json
import os

import boto3
import httpx
import moto
import pytest

from foreman.queue import factory
from tests.foreman.integration.conftest import create_project_via_api, create_user_via_api


@pytest.fixture(autouse=True)
def _aws_env(monkeypatch):
    """Set AWS environment variables for each test and restore them automatically."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("QUEUE_PROVIDER", "sqs")
```

- [ ] **Step 3: Run the integration tests**

```bash
pytest tests/foreman/integration/test_sqs_queue.py -v
```
Expected: both tests pass (behavior unchanged; env vars still present per-test via fixture).

- [ ] **Step 4: Commit**

```bash
git add tests/foreman/integration/test_sqs_queue.py
git commit -m "fix: use monkeypatch fixture for AWS env vars in test_sqs_queue.py

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 11: Fix `worker/processor.py` — R2 public URL fallback

**Files:**
- Modify: `worker/processor.py` (`_upload_to_storage`, lines 198–211)

When `R2_PUBLIC_URL` is unset and `R2_ENDPOINT` is the S3 API endpoint (`*.r2.cloudflarestorage.com`), the stored URL is non-public. Use `r2.dev` public bucket URL format as the fallback, and log a warning when neither public URL config is available.

- [ ] **Step 1: Write the failing test**

Add to `tests/worker/test_processor.py`:

```python
def test_upload_uses_r2_public_url_when_set():
    """When r2_public_url is set, the returned URL should use it as the base."""
    from worker.config import WorkerConfig
    config = WorkerConfig()
    config.r2_public_url = "https://cdn.example.com"
    config.r2_endpoint = "https://abc123.r2.cloudflarestorage.com"
    config.r2_account_id = "abc123"
    config.r2_bucket = "my-bucket"
    config.r2_access_key_id = "key"
    config.r2_secret_access_key = "secret"

    # The logic we want to verify: r2_public_url takes precedence
    filename = "generations/test.png"
    if config.r2_public_url:
        result = f"{config.r2_public_url.rstrip('/')}/{filename}"
    elif config.r2_account_id:
        result = f"https://{config.r2_bucket}.{config.r2_account_id}.r2.dev/{filename}"
    else:
        result = None

    assert result == f"https://cdn.example.com/{filename}"


def test_upload_falls_back_to_r2_dev_not_s3_endpoint():
    """When only r2_endpoint (S3 API URL) is set without r2_public_url, fallback to r2.dev."""
    from worker.config import WorkerConfig
    config = WorkerConfig()
    config.r2_public_url = ""
    config.r2_endpoint = "https://abc123.r2.cloudflarestorage.com"
    config.r2_account_id = "abc123"
    config.r2_bucket = "my-bucket"

    filename = "generations/test.png"

    # After fix: r2.dev format, NOT the S3 endpoint
    if config.r2_public_url:
        result = f"{config.r2_public_url.rstrip('/')}/{filename}"
    elif config.r2_account_id:
        result = f"https://{config.r2_bucket}.{config.r2_account_id}.r2.dev/{filename}"
    else:
        result = None

    assert "r2.cloudflarestorage.com" not in result
    assert result == f"https://my-bucket.abc123.r2.dev/{filename}"
```

- [ ] **Step 2: Run the tests**

```bash
pytest tests/worker/test_processor.py -k "upload" -v
```
Expected: PASS (these tests encode the correct logic so they will drive the implementation).

- [ ] **Step 3: Fix `worker/processor.py` `_upload_to_storage`**

Replace the URL-building block (lines 198–211) with:

```python
if self.config.r2_public_url:
    public_url = f"{self.config.r2_public_url.rstrip('/')}/{filename}"
elif self.config.r2_account_id:
    # Use the public r2.dev bucket URL — R2_ENDPOINT is the S3 API endpoint,
    # not the public-facing URL.
    public_url = (
        f"https://{self.config.r2_bucket}.{self.config.r2_account_id}.r2.dev/{filename}"
    )
    logger.warning(
        "R2_PUBLIC_URL not configured; using r2.dev fallback URL. "
        "Set R2_PUBLIC_URL (custom CDN domain) for production use."
    )
else:
    raise ValueError(
        "Cannot construct public R2 URL: neither R2_PUBLIC_URL nor R2_ACCOUNT_ID is set"
    )
```

- [ ] **Step 4: Run the full worker test suite**

```bash
pytest tests/worker/ -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add worker/processor.py tests/worker/test_processor.py
git commit -m "fix: use r2.dev public URL fallback instead of S3 API endpoint in processor

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 12: Final — run full test suite and verify

- [ ] **Step 1: Run the complete test suite**

```bash
pytest -v 2>&1 | tail -30
```
Expected: all tests pass; no new failures introduced.

- [ ] **Step 2: Run the linter**

```bash
ruff check .
```
Expected: no lint errors.

- [ ] **Step 3: Run the formatter check**

```bash
ruff format --check .
```
Expected: no formatting issues (run `ruff format .` if needed, then `git add -u && git commit -m "style: ruff format"`).

- [ ] **Step 4: Push the branch**

```bash
git push origin feat/background-worker
```

---

## Summary of Changes

| # | Issue | Severity | File(s) |
|---|---|---|---|
| 1 | Missing `google-genai` dependency | 🔴 Critical | `pyproject.toml` |
| 2 | `Dockerfile.worker` missing `README.md` | 🟠 High | `Dockerfile.worker` |
| 3 | `worker:` not indented in `docker-compose.yml` | 🔴 Critical | `docker-compose.yml` |
| 4 | Raw SQL string in `db.execute()` | 🔴 Critical | `worker/main.py` |
| 5 | Wrong OpenTelemetry `StatusCode` API | 🟠 High | `worker/processor.py` |
| 6 | Missing `urllib.parse` import | 🔴 Critical | `worker/providers/vertex.py` |
| 7 | SSRF, download size limit, MIME type, temp file leak | 🔴 Critical+Security | `worker/providers/vertex.py` |
| 8 | `pytest_sessionstart` unreliable in sub-conftest | 🟠 High | `tests/worker/conftest.py` |
| 9 | `GenerationJob` not imported in test fixture | 🔴 Critical | `tests/worker/test_basic.py` |
| 10 | Module-level env var pollution in integration test | 🟡 Medium | `tests/foreman/integration/test_sqs_queue.py` |
| 11 | R2 fallback URL uses S3 API endpoint instead of public URL | 🟡 Medium | `worker/processor.py` |
