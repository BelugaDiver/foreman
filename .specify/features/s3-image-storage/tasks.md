# Tasks: S3 Image Storage Provider

**Feature Branch**: `s3-image-storage`
**Spec**: `.specify/features/s3-image-storage/spec.md`
**Plan**: `.specify/features/s3-image-storage/plan.md`
**Generated**: 2026-05-01

---

## Overview

13 tasks across 4 phases. Phases 1–2 build the storage layer (can be partially parallelised); Phases 3–4 wire the worker and add test coverage. No task requires a running AWS environment — all tests use mocks.

**Dependency order at a glance**:

```
TASK-001 → TASK-003 → TASK-004
TASK-001 → TASK-003 → TASK-005
TASK-002 → TASK-003
TASK-003 → TASK-006
TASK-004 → TASK-007
TASK-003 → TASK-007
TASK-007 → TASK-008
TASK-008 → TASK-009
TASK-003 → TASK-010
TASK-004 → TASK-010
TASK-003 → TASK-011
TASK-007 → TASK-012
TASK-005 → TASK-013
```

---

## Phase 1 — Storage Layer Foundation

> Goal: a complete, factory-wired `S3Storage` with a fixed `is_configured` and the new `upload_file` method on `StorageProtocol` and `R2Storage`.

---

### TASK-001 — Fix `S3Settings.is_configured` for IAM role delegation

**Dependencies**: none

**Files to modify**:
- `foreman/storage/settings.py`

**What to do**:

Replace the `is_configured` property on `S3Settings` (currently `return bool(self.access_key_id and self.secret_access_key)`) with the IAM-aware logic from the plan:

```python
@property
def is_configured(self) -> bool:
    both_empty = not self.access_key_id and not self.secret_access_key
    both_present = bool(self.access_key_id and self.secret_access_key)
    return both_present or both_empty
```

The fix makes `is_configured` return `True` when **neither** key is provided (delegating to boto3's default credential chain / IAM roles) and `False` only when exactly one of the two is set (partial / broken config).

**Acceptance criteria**:
- `S3Settings(access_key_id="k", secret_access_key="s", ...).is_configured` → `True`
- `S3Settings(access_key_id=None, secret_access_key=None, ...).is_configured` → `True`
- `S3Settings(access_key_id="k", secret_access_key=None, ...).is_configured` → `False`
- `S3Settings(access_key_id=None, secret_access_key="s", ...).is_configured` → `False`
- All existing `R2Settings` tests continue to pass (`pytest tests/foreman/test_r2_storage.py`).

---

### TASK-002 — Extend `StorageProtocol` with `upload_file` abstract method

**Dependencies**: none

**Files to modify**:
- `foreman/storage/protocol.py`

**What to do**:

Add a fourth abstract method to `StorageProtocol` after the existing `delete` method:

```python
@abstractmethod
async def upload_file(self, local_path: str, storage_key: str) -> None:
    """Upload a local file directly to storage at the given key.

    Args:
        local_path: Absolute path of the local file to upload.
        storage_key: Destination key in the storage bucket.
    """
```

Do not modify any other method or docstring in the file.

**Acceptance criteria**:
- `StorageProtocol` has four abstract methods: `create_upload_url`, `get_download_url`, `delete`, `upload_file`.
- Attempting to instantiate a concrete subclass that omits `upload_file` raises `TypeError`.
- `pytest --collect-only` succeeds (no import errors from the change).

---

### TASK-003 — Implement `S3Storage` class

**Dependencies**: TASK-001, TASK-002

**Files to create**:
- `foreman/storage/s3_storage.py`

**What to do**:

Create `S3Storage` implementing all four `StorageProtocol` methods. Mirror the structure of `foreman/storage/r2_storage.py`. Key differences from `R2Storage`:

- No `endpoint_url` argument to `boto3.client` — standard AWS endpoint.
- Client constructed with `region_name=settings.region`.
- Explicit credentials passed only when `settings.access_key_id` is truthy (IAM-role path skips them).
- `upload_file` and `delete` use `asyncio.to_thread` (blocking I/O).
- `get_download_url` returns `{public_url}/{key}` when `settings.public_url` is set, otherwise a 1-hour presigned GET URL.
- `create_upload_url` generates a 1-hour presigned PUT URL bound to the provided `ContentType`, key pattern `projects/{project_id}/{uuid}/{filename}`.
- `delete` returns `False` (without raising) on `ClientError`, logs at `ERROR` level.
- `_ensure_client` raises `ValueError` with message: `"S3Storage is not configured. Set S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY (or use IAM roles), S3_BUCKET, and S3_REGION environment variables."` when `self._client is None`.
- Structured `INFO` log on successful init (`bucket`, `region` attributes); `WARNING` log when `not settings.is_configured`.
- Every AWS-calling method (`create_upload_url`, `get_download_url` when generating presigned, `delete`, `upload_file`) must be wrapped in an OpenTelemetry span recording `storage_key`, `bucket`, and outcome.

```python
# foreman/storage/s3_storage.py  (sketch — implement fully)
import asyncio, uuid
from datetime import datetime, timedelta, timezone
import boto3
from botocore.exceptions import ClientError
from opentelemetry import trace
from foreman.logging_config import get_logger
from foreman.storage.protocol import StorageProtocol, UploadIntent
from foreman.storage.settings import S3Settings

logger = get_logger("foreman.storage.s3")
tracer = trace.get_tracer(__name__)

class S3Storage(StorageProtocol):
    def __init__(self, settings: S3Settings) -> None: ...
    def _ensure_client(self) -> None: ...
    async def create_upload_url(self, filename, content_type, project_id) -> UploadIntent: ...
    async def get_download_url(self, storage_key: str) -> str: ...
    async def delete(self, storage_key: str) -> bool: ...
    async def upload_file(self, local_path: str, storage_key: str) -> None: ...
```

**Acceptance criteria**:
- `S3Storage(S3Settings(access_key_id="k", secret_access_key="s", bucket="b", region="us-east-1"))` constructs without error.
- `S3Storage(S3Settings(access_key_id=None, secret_access_key=None, bucket="b", region="us-east-1"))` constructs without error (IAM path).
- Calling any operation on an unconfigured instance (partially set creds) raises `ValueError` containing the expected env var names.
- `get_download_url` with `public_url` set returns `{public_url}/{key}` without calling boto3.
- `get_download_url` without `public_url` calls `generate_presigned_url("get_object", ...)`.
- `delete` returns `False` on `ClientError` without raising.
- `upload_file` calls `client.upload_fileobj` via `asyncio.to_thread`.
- `pytest --collect-only` succeeds.

---

### TASK-004 — Add `upload_file` to `R2Storage`

**Dependencies**: TASK-002

**Files to modify**:
- `foreman/storage/r2_storage.py`

**What to do**:

`R2Storage` now fails the abstract interface because `upload_file` is abstract on `StorageProtocol`. Add the concrete implementation:

```python
async def upload_file(self, local_path: str, storage_key: str) -> None:
    """Upload a local file directly to R2 at the given storage key."""
    self._ensure_client()
    with open(local_path, "rb") as f:
        await asyncio.to_thread(
            self._client.upload_fileobj,
            f,
            self._bucket,
            storage_key,
            ExtraArgs={"ContentType": "image/png"},
        )
    logger.info("Uploaded file to R2", extra={"storage_key": storage_key})
```

`asyncio` is already imported in `r2_storage.py` as `anyio`; check whether `asyncio.to_thread` is used or if `anyio.to_thread.run_sync` should be used consistently. Use whichever pattern the existing file uses for blocking calls (currently the file uses no blocking calls, so use `asyncio.to_thread` matching the plan and `S3Storage`).

Add `import asyncio` at the top of the file if not already present.

**Acceptance criteria**:
- `R2Storage` instantiates without `TypeError` (fulfils the updated abstract interface).
- `upload_file` calls `client.upload_fileobj` via `asyncio.to_thread`.
- Calling `upload_file` on an unconfigured `R2Storage` raises `ValueError` (via `_ensure_client`).
- `pytest tests/foreman/test_r2_storage.py` passes.

---

### TASK-005 — Update storage factory for `STORAGE_PROVIDER=s3`

**Dependencies**: TASK-003

**Files to modify**:
- `foreman/storage/factory.py`

**What to do**:

Add the `s3` branch and improve the error message for unknown providers:

```python
from foreman.storage.s3_storage import S3Storage
from foreman.storage.settings import R2Settings, S3Settings

@lru_cache(maxsize=1)
def get_storage() -> StorageProtocol:
    provider = os.getenv("STORAGE_PROVIDER", "r2").lower()
    logger.debug("Initializing storage", extra={"provider": provider})

    if provider == "r2":
        storage = R2Storage(R2Settings.from_env())
        logger.info("Storage initialized", extra={"provider": provider})
        return storage

    if provider == "s3":
        storage = S3Storage(S3Settings.from_env())
        logger.info("Storage initialized", extra={"provider": provider})
        return storage

    raise ValueError(
        f"Unknown STORAGE_PROVIDER: {provider!r}. Valid values: r2, s3"
    )
```

**Acceptance criteria**:
- `STORAGE_PROVIDER=s3` (mocked env) → `get_storage()` returns an `S3Storage` instance.
- `STORAGE_PROVIDER=r2` → `get_storage()` returns an `R2Storage` instance (regression).
- `STORAGE_PROVIDER=gcs` → `get_storage()` raises `ValueError` mentioning `r2, s3`.
- Cache is shared across both branches (`lru_cache` unchanged).

---

### TASK-006 — Export `S3Storage` from `foreman/storage/__init__.py`

**Dependencies**: TASK-003, TASK-005

**Files to modify**:
- `foreman/storage/__init__.py`

**What to do**:

Add `S3Storage` to the import and to `__all__`:

```python
from foreman.storage.factory import get_storage, get_storage_sync
from foreman.storage.protocol import StorageProtocol, UploadIntent
from foreman.storage.r2_storage import R2Storage
from foreman.storage.s3_storage import S3Storage

__all__ = [
    "StorageProtocol",
    "UploadIntent",
    "R2Storage",
    "S3Storage",
    "get_storage",
    "get_storage_sync",
]
```

**Acceptance criteria**:
- `from foreman.storage import S3Storage` succeeds without error.
- `from foreman.storage import get_storage` still works (regression).
- `pytest --collect-only` shows no import errors.

---

## Phase 2 — Worker Refactoring

> Goal: `JobProcessor._upload_to_storage` uses `StorageProtocol`; no raw boto3 in `processor.py`; SSRF allowlist covers S3 domains.

---

### TASK-007 — Refactor `JobProcessor._upload_to_storage` to use `StorageProtocol`

**Dependencies**: TASK-003, TASK-004

**Files to modify**:
- `worker/processor.py`

**What to do**:

1. Remove `import boto3` and `from botocore.config import Config as BotoConfig` from the top of the file.
2. Add `from foreman.storage.protocol import StorageProtocol` to the imports.
3. Add `storage: StorageProtocol` as the fourth positional parameter to `JobProcessor.__init__`:
   ```python
   def __init__(self, db: Database, config: WorkerConfig, ai_provider, storage: StorageProtocol) -> None:
       self.db = db
       self.config = config
       self.ai_provider = ai_provider
       self._storage = storage
   ```
4. Replace the entire body of `_upload_to_storage` with:
   ```python
   async def _upload_to_storage(self, local_path: str) -> str:
       """Upload generated image via StorageProtocol and return the download URL."""
       with tracer.start_as_current_span("upload_to_storage") as span:
           storage_key = f"generations/{uuid.uuid4()}.png"
           span.set_attribute("storage_key", storage_key)
           try:
               await self._storage.upload_file(local_path, storage_key)
               url = await self._storage.get_download_url(storage_key)
               span.set_attribute("output_url", url)
               logger.info("Uploaded to storage", extra={"storage_key": storage_key})
               return url
           finally:
               try:
                   os.unlink(local_path)
               except OSError:
                   pass
   ```
   The old docstring referred to "R2 storage" — update it as shown above.

5. The `config` parameter no longer needs R2 credentials for upload (they are encapsulated in the injected `StorageProtocol`). Do **not** remove `config` from `__init__` — it is still used for other worker settings.

**Acceptance criteria**:
- `grep -n "import boto3\|BotoConfig\|r2_access_key\|r2_secret" worker/processor.py` returns no matches.
- `JobProcessor` cannot be instantiated without a `storage` argument.
- `_upload_to_storage` calls `self._storage.upload_file` then `self._storage.get_download_url`.
- Local temp file is deleted in the `finally` block whether upload succeeds or fails.
- `pytest tests/worker/` passes (after TASK-012 updates test fixtures).

---

### TASK-008 — Inject `StorageProtocol` into `JobProcessor` from `worker/main.py`

**Dependencies**: TASK-007

**Files to modify**:
- `worker/main.py`

**What to do**:

1. Add the import at the top of `worker/main.py`:
   ```python
   from foreman.storage import get_storage
   ```
2. In the `main()` function, call `get_storage()` after the `ai_provider` initialisation and before `JobProcessor` construction, and pass it to the constructor:
   ```python
   storage = get_storage()
   processor = JobProcessor(db, config, ai_provider, storage)
   ```
   The line `processor = JobProcessor(db, config, ai_provider)` must be replaced — do not leave the old call.

**Acceptance criteria**:
- `worker/main.py` contains `from foreman.storage import get_storage`.
- `JobProcessor(db, config, ai_provider, storage)` is the only instantiation of `JobProcessor` in `worker/main.py`.
- `python -c "import worker.main"` succeeds without error (no import-time side effects from `get_storage` at import time — the call is inside `main()`).

---

### TASK-009 — Update `WorkerConfig.get_allowed_image_domains` to include S3 domains

**Dependencies**: TASK-008

**Files to modify**:
- `worker/config.py`

**What to do**:

Extend `get_allowed_image_domains` to also extract hostnames from `S3_PUBLIC_URL` and from the S3 virtual-host bucket domain when `S3_BUCKET` is set. Read from environment directly inside the method (matching the style of the existing R2 fields which read from `self.*` attributes populated from env at init time — but since there are no `s3_*` fields on `WorkerConfig`, use `os.getenv` directly in the method):

```python
def get_allowed_image_domains(self) -> set[str]:
    """Get allowed domains for input image downloads (SSRF protection)."""
    domains = set()
    # R2
    if self.r2_public_url:
        parsed = urllib.parse.urlparse(self.r2_public_url)
        if parsed.hostname:
            domains.add(parsed.hostname)
    if self.r2_endpoint:
        parsed = urllib.parse.urlparse(self.r2_endpoint)
        if parsed.hostname:
            domains.add(parsed.hostname)
    # S3
    s3_public_url = os.getenv("S3_PUBLIC_URL")
    if s3_public_url:
        parsed = urllib.parse.urlparse(s3_public_url)
        if parsed.hostname:
            domains.add(parsed.hostname)
    s3_bucket = os.getenv("S3_BUCKET")
    s3_region = os.getenv("S3_REGION", "us-east-1")
    if s3_bucket:
        domains.add(f"{s3_bucket}.s3.{s3_region}.amazonaws.com")
    return domains
```

`os` is already imported in `worker/config.py`.

**Acceptance criteria**:
- With `S3_PUBLIC_URL=https://cdn.example.com` and `S3_BUCKET=my-bucket` and `S3_REGION=eu-west-1` in the environment, `get_allowed_image_domains()` includes `cdn.example.com` and `my-bucket.s3.eu-west-1.amazonaws.com`.
- With no S3 env vars set, the result is unchanged from the current behaviour (only R2 domains).
- Existing R2 domain extraction is not modified.
- `pytest tests/worker/test_config_extra.py` passes.

---

## Phase 3 — Configuration & Documentation

---

### TASK-010 — Add S3 configuration block to `.env.foreman.example`

**Dependencies**: TASK-003, TASK-004 (so the comment accurately reflects what is implemented)

**Files to modify**:
- `.env.foreman.example`

**What to do**:

Locate the existing R2 configuration block (lines containing `R2_*` variables). Immediately after that block, add a blank line and the following S3 block:

```bash
# ── Amazon S3 Storage (alternative to Cloudflare R2) ─────────────────────────
# Set STORAGE_PROVIDER=s3 and provide the variables below.
# Credentials are optional when deploying on AWS with an IAM role/instance profile.
#
# STORAGE_PROVIDER=s3
# S3_BUCKET=foreman-images
# S3_REGION=us-east-1
# S3_ACCESS_KEY_ID=your_access_key_id       # optional if using IAM roles
# S3_SECRET_ACCESS_KEY=your_secret_access_key  # optional if using IAM roles
# S3_PUBLIC_URL=https://cdn.example.com     # optional; use CloudFront or other CDN
```

Do not change any existing lines in the file.

**Acceptance criteria**:
- All six `S3_*` variables are documented in the example file.
- The comment notes that `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` are optional for IAM-role deployments.
- `STORAGE_PROVIDER=s3` is shown.
- The comment about `S3_PUBLIC_URL` mentions CDN/CloudFront.

---

## Phase 4 — Test Coverage

---

### TASK-011 — Write unit tests for `S3Storage`

**Dependencies**: TASK-003

**Files to create**:
- `tests/foreman/test_s3_storage.py`

**What to do**:

Mirror the structure of `tests/foreman/test_r2_storage.py`. Use `pytest` + `unittest.mock`. Cover every branch in `S3Storage`:

| Test name | What it asserts |
|---|---|
| `test_initialization_with_explicit_creds` | boto3 client created with `aws_access_key_id` / `aws_secret_access_key` when both provided |
| `test_initialization_with_iam_role` | boto3 client created without explicit keys when both are `None`; no error |
| `test_initialization_unconfigured_logs_warning` | When `is_configured` is `False` (one key set, one not), `_client` is `None` after init |
| `test_ensure_client_raises_value_error_when_unconfigured` | `_ensure_client()` raises `ValueError` containing env var names |
| `test_create_upload_url_returns_upload_intent` | Returns `UploadIntent` with `upload_url`, `file_key` matching `projects/{project_id}/...`, `expires_at` ~1 hour from now |
| `test_create_upload_url_key_pattern` | `file_key` matches `projects/{project_id}/{uuid}/{filename}` |
| `test_create_upload_url_binds_content_type` | Presigned URL call includes `ContentType` param |
| `test_get_download_url_uses_public_url` | When `public_url` is set, returns `{public_url}/{key}`, no boto3 call |
| `test_get_download_url_generates_presigned` | When `public_url` is `None`, calls `generate_presigned_url("get_object", ...)` |
| `test_delete_returns_true_on_success` | Returns `True` when `delete_object` succeeds |
| `test_delete_returns_false_on_client_error` | Returns `False` and does not raise when `ClientError` is raised |
| `test_upload_file_calls_upload_fileobj_via_thread` | Calls `asyncio.to_thread` with `client.upload_fileobj` |
| `test_upload_file_raises_when_unconfigured` | Raises `ValueError` when storage is not configured |

Use `@pytest.mark.asyncio` for async tests. Patch `foreman.storage.s3_storage.boto3.client` for tests that should not make real AWS calls.

**Acceptance criteria**:
- `pytest tests/foreman/test_s3_storage.py -v` exits 0.
- All 13 tests listed above are present and passing.
- No real AWS/S3 calls are made (all boto3 usage is mocked).

---

### TASK-012 — Update `tests/worker/test_processor.py` to mock `StorageProtocol`

**Dependencies**: TASK-007

**Files to modify**:
- `tests/worker/test_processor.py`

**What to do**:

`JobProcessor.__init__` now requires a `storage: StorageProtocol` argument. Update all test helpers and fixtures to supply a mock:

1. Add a `_make_storage()` helper that returns an `AsyncMock` with `upload_file` and `get_download_url` configured:
   ```python
   def _make_storage(download_url: str = "https://cdn.example.com/generations/test.png") -> AsyncMock:
       storage = AsyncMock()
       storage.upload_file = AsyncMock(return_value=None)
       storage.get_download_url = AsyncMock(return_value=download_url)
       return storage
   ```

2. Update `_make_processor` to accept an optional `storage` kwarg and pass it to `JobProcessor`:
   ```python
   def _make_processor(config=None, ai_provider=None, storage=None) -> JobProcessor:
       db = MagicMock()
       return JobProcessor(
           db=db,
           config=config or _make_config(),
           ai_provider=ai_provider or MagicMock(),
           storage=storage or _make_storage(),
       )
   ```

3. Find every existing test that patches `boto3` or `BotoConfig` in the context of `_upload_to_storage` and remove those patches. Replace with assertions against the mock `StorageProtocol` instead.

4. Add or update an `_upload_to_storage` test suite covering:
   - `test_upload_to_storage_calls_upload_file_and_get_download_url` — asserts both protocol methods called with correct args.
   - `test_upload_to_storage_deletes_local_file_on_success` — asserts `os.unlink` called after upload.
   - `test_upload_to_storage_deletes_local_file_on_failure` — asserts `os.unlink` called even when `upload_file` raises.
   - `test_upload_to_storage_propagates_storage_error` — asserts exception from `upload_file` propagates out of `_upload_to_storage`.

5. Add a regression test for the R2 path:
   - `test_process_with_r2_storage_via_protocol` — `_make_storage()` backed by an `R2Storage` mock; assert `process()` returns `ProcessingResult(success=True)`.

**Acceptance criteria**:
- `grep -n "boto3\|BotoConfig\|r2_access_key\|r2_secret" tests/worker/test_processor.py` returns no matches.
- `pytest tests/worker/test_processor.py -v` exits 0.
- The four new `_upload_to_storage` tests and one regression test are present and passing.

---

### TASK-013 — Add factory tests for `s3` provider routing

**Dependencies**: TASK-005

**Files to modify**:
- `tests/foreman/` — add tests to an existing storage test file, or create `tests/foreman/test_storage_factory.py` if no factory test file exists.

Check whether `tests/foreman/` already contains a factory test file (`test_factory.py` or similar). If not, create `tests/foreman/test_storage_factory.py`.

**What to do**:

Cover the factory routing logic (always reset `lru_cache` between tests using `get_storage.cache_clear()`):

| Test name | What it asserts |
|---|---|
| `test_factory_returns_r2_storage_by_default` | `STORAGE_PROVIDER` unset → `get_storage()` returns `R2Storage` |
| `test_factory_returns_r2_storage_when_set` | `STORAGE_PROVIDER=r2` → `get_storage()` returns `R2Storage` |
| `test_factory_returns_s3_storage_when_set` | `STORAGE_PROVIDER=s3` → `get_storage()` returns `S3Storage` |
| `test_factory_raises_for_unknown_provider` | `STORAGE_PROVIDER=gcs` → `get_storage()` raises `ValueError` with message containing `r2, s3` |
| `test_factory_is_case_insensitive` | `STORAGE_PROVIDER=S3` (uppercase) → `get_storage()` returns `S3Storage` |

Use `monkeypatch.setenv` (pytest fixture) or `unittest.mock.patch.dict(os.environ, ...)` to set env vars. Call `get_storage.cache_clear()` in a `teardown` / `autouse` fixture to prevent cache bleed between tests.

**Acceptance criteria**:
- `pytest tests/foreman/test_storage_factory.py -v` (or whichever file contains these tests) exits 0.
- All 5 factory tests are present.
- Cache is cleared between each test (no test ordering dependency).

---

## Parallel Execution Guide

The following tasks have no dependency on each other and can be worked in parallel:

| Parallel group | Tasks |
|---|---|
| A — Storage foundation (independent) | TASK-001, TASK-002 |
| B — After TASK-002 | TASK-004 can start immediately after TASK-002 |
| C — After TASK-001 + TASK-002 | TASK-003, which unblocks TASK-005, TASK-006, TASK-011 |
| D — After TASK-003 + TASK-004 | TASK-007 (and TASK-010 for docs) |
| E — After TASK-007 | TASK-008, TASK-012 |
| F — After TASK-008 | TASK-009, TASK-013 |

Suggested MVP execution order (one developer, sequential):
`TASK-001 → TASK-002 → TASK-004 → TASK-003 → TASK-005 → TASK-006 → TASK-007 → TASK-008 → TASK-009 → TASK-010 → TASK-011 → TASK-012 → TASK-013`

---

## Checklist

- [X] TASK-001 Fix `S3Settings.is_configured` for IAM role delegation in `foreman/storage/settings.py`
- [X] TASK-002 Extend `StorageProtocol` with `upload_file` abstract method in `foreman/storage/protocol.py`
- [X] TASK-003 Implement `S3Storage` class in `foreman/storage/s3_storage.py`
- [X] TASK-004 [P] Add `upload_file` to `R2Storage` in `foreman/storage/r2_storage.py`
- [X] TASK-005 Update storage factory for `STORAGE_PROVIDER=s3` in `foreman/storage/factory.py`
- [X] TASK-006 Export `S3Storage` from `foreman/storage/__init__.py`
- [X] TASK-007 Refactor `JobProcessor._upload_to_storage` to use `StorageProtocol` in `worker/processor.py`
- [X] TASK-008 Inject `StorageProtocol` into `JobProcessor` from `worker/main.py`
- [X] TASK-009 Update `WorkerConfig.get_allowed_image_domains` for S3 in `worker/config.py`
- [X] TASK-010 [P] Add S3 config block to `.env.foreman.example`
- [X] TASK-011 Write unit tests for `S3Storage` in `tests/foreman/test_s3_storage.py`
- [X] TASK-012 Update processor tests to mock `StorageProtocol` in `tests/worker/test_processor.py`
- [X] TASK-013 Add factory tests for `s3` provider routing in `tests/foreman/test_storage_factory.py`
