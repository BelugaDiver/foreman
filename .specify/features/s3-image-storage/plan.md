# Implementation Plan: S3 Image Storage Provider

**Feature Branch**: `s3-image-storage`
**Spec**: `.specify/features/s3-image-storage/spec.md`
**Status**: Planning

---

## 1. Architecture & Design Decisions

### 1.1 StorageProtocol Extension — `upload_file`

**Decision**: Add a fourth abstract method `upload_file(local_path: str, storage_key: str) -> None` to `StorageProtocol`.

**Rationale**: The worker's `_upload_to_storage` holds a local file path and needs to PUT bytes directly — it cannot use `create_upload_url` (a browser-client-oriented presigned PUT flow) to upload the file without re-introducing raw boto3. Adding `upload_file` to the protocol is the only way to give the worker a provider-agnostic direct upload call without leaking storage internals. Both `R2Storage` and `S3Storage` implement it using `asyncio.to_thread(client.upload_fileobj, ...)`.

**Rejected alternatives**:
- *Worker calls `create_upload_url` for the key, then uploads via raw boto3*: still violates FR-012 (inline client construction remains).
- *Worker calls `create_upload_url` and PUTs via `httpx` to the presigned URL*: introduces unnecessary HTTP round-trip and a new dependency.
- *No protocol change; worker accesses `storage._client` directly*: violates the abstraction entirely.

**Post-upload URL flow**: After calling `upload_file(path, key)`, the worker calls `get_download_url(key)` to obtain the URL to persist as `output_image_url`. With `S3_PUBLIC_URL` set this is a stable CDN URL; without it, a 1-hour presigned GET URL is stored (acceptable for MVP since the API regenerates URLs on each download request from `image.storage_key`).

### 1.2 Worker StorageProtocol Injection

**Decision**: `JobProcessor.__init__` gains a `storage: StorageProtocol` parameter. `worker/main.py` calls `get_storage()` (the shared factory) and passes the instance to `JobProcessor`.

**Rationale**: Constructor injection is the simplest, most testable pattern. The `lru_cache` on `get_storage()` means calling it in worker bootstrap is cost-free. No separate worker factory is needed (Open Question 1 resolved: shared factory is acceptable).

### 1.3 S3Settings / WorkerConfig Credential Strategy

**Decision**: Reuse the existing `S3Settings.from_env()` which reads `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` / `S3_REGION` / `S3_BUCKET`. The worker does **not** reuse `aws_access_key_id` / `aws_secret_access_key` for S3 storage — those fields remain dedicated to SQS. No new fields are added to `WorkerConfig`; the worker bootstrap calls `S3Settings.from_env()` via `get_storage()`.

**Rationale**: Separating SQS credentials (`AWS_*`) from storage credentials (`S3_*`) gives operators orthogonal control (e.g. least-privilege IAM per service). `S3Settings.from_env()` already reads the correct env vars. `WorkerConfig` gains no S3-specific fields; it only needs `storage_provider` to pass the right `STORAGE_PROVIDER` value if it differs from the default env (but since `STORAGE_PROVIDER` is a global env var, no WorkerConfig field is needed at all).

### 1.4 boto3 Thread Safety & Async

**Decision**: All blocking boto3 network calls in `S3Storage` (`upload_fileobj`, `delete_object`) use `asyncio.to_thread()`. Presigned URL generation (`generate_presigned_url`) is a local/crypto-only operation and is called synchronously, consistent with `R2Storage`.

**Rationale**: FR-006 requires `asyncio.to_thread` for blocking calls. Presigned URL generation has no I/O and does not block the event loop meaningfully (consistent with existing R2 approach).

### 1.5 S3Settings `is_configured` — IAM Role Support

**Decision**: `S3Settings.is_configured` returns `True` even when `access_key_id` and `secret_access_key` are both `None`/empty — trusting boto3's default credential chain (IAM roles, instance profiles). The existing code already returns `bool(self.access_key_id and self.secret_access_key)` which would be `False` for IAM-role-only deployments. **This must be updated** to return `True` also when both are `None` (not just empty string), delegating to boto3. This matches the spec assumption and FR-011.

Updated logic:
```python
@property
def is_configured(self) -> bool:
    # True if explicit creds provided, OR if neither is set (IAM role delegation)
    both_empty = not self.access_key_id and not self.secret_access_key
    both_present = bool(self.access_key_id and self.secret_access_key)
    return both_present or both_empty
```

### 1.6 SSRF Allowlist for S3

**Decision**: `WorkerConfig.get_allowed_image_domains()` is extended to also parse `S3_PUBLIC_URL` and the S3 bucket virtual-host domain (`{bucket}.s3.{region}.amazonaws.com`) when `STORAGE_PROVIDER=s3`.

**Rationale**: The spec (Security section) requires the worker's SSRF allowlist to include S3 domains so that AI-generated images stored in S3 can be used as `input_image_url` in chained generation requests.

---

## 2. Component Breakdown

### Files to Create

| File | Purpose |
|------|---------|
| `foreman/storage/s3_storage.py` | New `S3Storage` class implementing `StorageProtocol` |
| `tests/foreman/test_s3_storage.py` | Unit tests for all `S3Storage` method paths |

### Files to Modify

| File | Changes |
|------|---------|
| `foreman/storage/protocol.py` | Add `upload_file(local_path, storage_key)` abstract method |
| `foreman/storage/r2_storage.py` | Add `upload_file` implementation |
| `foreman/storage/factory.py` | Add `elif provider == "s3"` branch; import `S3Storage`, `S3Settings` |
| `foreman/storage/__init__.py` | Export `S3Storage` in `__all__` |
| `foreman/storage/settings.py` | Fix `S3Settings.is_configured` to support IAM role delegation |
| `worker/processor.py` | Add `storage: StorageProtocol` to `__init__`; refactor `_upload_to_storage` to use protocol; remove `boto3` import |
| `worker/main.py` | Call `get_storage()` and pass to `JobProcessor` |
| `worker/config.py` | Update `get_allowed_image_domains` to include S3 domains |
| `.env.foreman.example` | Add commented S3 configuration block |
| `tests/worker/test_processor.py` | Update upload tests to mock `StorageProtocol` instead of boto3 |

---

## 3. Implementation Sequence

Steps are ordered so each builds on a stable foundation.

### Step 1 — Extend `StorageProtocol`
**File**: `foreman/storage/protocol.py`

Add the `upload_file` abstract method:
```python
@abstractmethod
async def upload_file(self, local_path: str, storage_key: str) -> None:
    """Upload a local file directly to storage at the given key."""
```

*Must be done first* — both storage implementations depend on it.

---

### Step 2 — Fix `S3Settings.is_configured`
**File**: `foreman/storage/settings.py`

Update `is_configured` property to treat "no explicit credentials" as valid (IAM role delegation), per the design decision in §1.5.

---

### Step 3 — Implement `S3Storage`
**File**: `foreman/storage/s3_storage.py`

Model closely on `R2Storage`. Key differences:
- No `endpoint_url` (standard AWS endpoint; virtual-hosted style)
- Client constructed with `region_name=settings.region`
- `upload_file` uses `asyncio.to_thread(client.upload_fileobj, ...)`
- `delete` uses `asyncio.to_thread(client.delete_object, ...)`
- OTel span per operation with `storage_key`, `bucket`, outcome attributes (FR-008)

Sketch:
```python
class S3Storage(StorageProtocol):
    def __init__(self, settings: S3Settings) -> None:
        self._settings = settings
        self._client = None
        self._bucket = settings.bucket

        if settings.is_configured:
            client_kwargs = dict(region_name=settings.region)
            if settings.access_key_id:
                client_kwargs["aws_access_key_id"] = settings.access_key_id
                client_kwargs["aws_secret_access_key"] = settings.secret_access_key
            self._client = boto3.client("s3", **client_kwargs)
            logger.info("S3 Storage initialized", extra={"bucket": self._bucket, "region": settings.region})
        else:
            logger.warning("S3 Storage not configured - operations will fail if attempted")

    def _ensure_client(self) -> None:
        if self._client is None:
            raise ValueError(
                "S3Storage is not configured. Set S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY "
                "(or use IAM roles), S3_BUCKET, and S3_REGION environment variables."
            )

    async def create_upload_url(self, filename, content_type, project_id) -> UploadIntent:
        # generate key, call generate_presigned_url("put_object") with ContentType
        ...

    async def get_download_url(self, storage_key) -> str:
        # return public_url/{key} if configured, else presigned GET
        ...

    async def delete(self, storage_key) -> bool:
        # asyncio.to_thread(client.delete_object, ...), return False on error
        ...

    async def upload_file(self, local_path, storage_key) -> None:
        # asyncio.to_thread(client.upload_fileobj, open(local_path), bucket, key)
        ...
```

---

### Step 4 — Add `upload_file` to `R2Storage`
**File**: `foreman/storage/r2_storage.py`

Implement the new `upload_file` abstract method (required since `R2Storage` extends `StorageProtocol`):
```python
async def upload_file(self, local_path: str, storage_key: str) -> None:
    self._ensure_client()
    with open(local_path, "rb") as f:
        await asyncio.to_thread(
            self._client.upload_fileobj, f, self._bucket, storage_key,
            ExtraArgs={"ContentType": "image/png"},
        )
```

---

### Step 5 — Update Storage Factory
**File**: `foreman/storage/factory.py`

```python
from foreman.storage.s3_storage import S3Storage
from foreman.storage.settings import R2Settings, S3Settings

@lru_cache(maxsize=1)
def get_storage() -> StorageProtocol:
    provider = os.getenv("STORAGE_PROVIDER", "r2").lower()
    if provider == "r2":
        return R2Storage(R2Settings.from_env())
    if provider == "s3":
        return S3Storage(S3Settings.from_env())
    raise ValueError(f"Unknown STORAGE_PROVIDER: {provider!r}. Valid values: r2, s3")
```

---

### Step 6 — Update `foreman/storage/__init__.py`
Add `S3Storage` to imports and `__all__`.

---

### Step 7 — Refactor `worker/processor.py`
**Changes**:
1. Remove `import boto3`, `from botocore.config import Config as BotoConfig`.
2. Add `storage: StorageProtocol` parameter to `JobProcessor.__init__`.
3. Replace `_upload_to_storage(self, local_path)` body with:
   ```python
   async def _upload_to_storage(self, local_path: str) -> str:
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
4. Store `self._storage = storage` in `__init__`.

---

### Step 8 — Update `worker/main.py`
Import `get_storage` from `foreman.storage` and pass the result to `JobProcessor`:
```python
from foreman.storage import get_storage

# in main():
storage = get_storage()
processor = JobProcessor(db, config, ai_provider, storage)
```

---

### Step 9 — Update `WorkerConfig.get_allowed_image_domains`
**File**: `worker/config.py`

Add S3 domain extraction:
```python
def get_allowed_image_domains(self) -> set[str]:
    domains = set()
    # R2
    for url in (self.r2_public_url, self.r2_endpoint):
        if url:
            parsed = urllib.parse.urlparse(url)
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

---

### Step 10 — Update `.env.foreman.example`
Add a commented S3 block after the existing R2 block:
```bash
# Amazon S3 Storage (alternative to Cloudflare R2)
# Set STORAGE_PROVIDER=s3 and configure the variables below.
# STORAGE_PROVIDER=s3
# S3_BUCKET=foreman-images
# S3_REGION=us-east-1
# S3_ACCESS_KEY_ID=your_access_key       # optional if using IAM roles
# S3_SECRET_ACCESS_KEY=your_secret_key   # optional if using IAM roles
# S3_PUBLIC_URL=https://cdn.example.com  # optional; use CDN/CloudFront for stable download URLs
```

---

## 4. Test Strategy

### 4.1 New: `tests/foreman/test_s3_storage.py`

Mirror the structure of `tests/foreman/test_r2_storage.py`. Cover:

| Test | Description |
|------|-------------|
| `test_initialization_with_explicit_creds` | Client constructed with explicit key/secret |
| `test_initialization_with_iam_role` | Client constructed without creds (IAM delegation); no error |
| `test_unconfigured_raises_on_operation` | `_ensure_client` raises `ValueError` with meaningful message |
| `test_create_upload_url_success` | Returns `UploadIntent` with S3 presigned URL, correct key pattern |
| `test_create_upload_url_binds_content_type` | Presigned URL params include `ContentType` |
| `test_get_download_url_with_public_url` | Returns `{S3_PUBLIC_URL}/{key}` without calling boto3 |
| `test_get_download_url_presigned` | Returns presigned GET URL when no `public_url` |
| `test_delete_returns_true_on_success` | Returns `True` after successful `delete_object` |
| `test_delete_returns_false_on_exception` | Returns `False` (no raise) when `ClientError` raised |
| `test_upload_file_calls_upload_fileobj` | `upload_fileobj` called with correct bucket/key |
| `test_upload_file_propagates_exception` | Raises on `ClientError` (not swallowed) |
| `test_otel_span_created_per_operation` | Spans created for `create_upload_url`, `delete`, `upload_file` |

### 4.2 Updated: `tests/worker/test_processor.py`

- Replace `_make_config()` helper with a `_make_storage()` helper returning a `MagicMock(spec=StorageProtocol)`.
- Update `_make_processor()` to accept and pass a `storage` argument.
- Replace `test_upload_to_storage_with_r2_public_url` / `test_upload_to_storage_r2_dev_fallback` with:
  - `test_upload_to_storage_uses_protocol` — verifies `storage.upload_file` and `storage.get_download_url` are called; no boto3 mock needed.
  - `test_upload_to_storage_propagates_error` — storage raises, exception propagates through `process()` and marks generation `failed`.
  - `test_upload_to_storage_cleans_up_local_file` — temp file is unlinked even on success.
  - `test_upload_to_storage_cleans_up_on_error` — temp file is unlinked even when upload fails.

### 4.3 Updated: `tests/foreman/test_storage_factory.py` (new or add to existing)

| Test | Description |
|------|-------------|
| `test_factory_returns_r2_storage` | `STORAGE_PROVIDER=r2` → `R2Storage` instance |
| `test_factory_returns_s3_storage` | `STORAGE_PROVIDER=s3` → `S3Storage` instance |
| `test_factory_raises_on_unknown_provider` | Unknown value raises `ValueError` |
| `test_factory_lru_cache_returns_same_instance` | Second call returns same cached object |

### 4.4 Regression: Existing R2 Tests

All existing tests in `tests/foreman/test_r2_storage.py` must still pass. The only change to `R2Storage` is adding `upload_file` — add one test for it mirroring the S3 variant.

### 4.5 Coverage Gate

SC-003 requires `pytest` exits 0 and coverage ≥ 85%. SC-004 requires 100% branch coverage of `S3Storage`. Use `pytest --cov=foreman --cov=worker --cov-report=term-missing` to verify.

---

## 5. Acceptance Checklist

- [ ] `STORAGE_PROVIDER=s3` starts API cleanly, `get_storage()` returns `S3Storage`
- [ ] `POST /projects/{id}/images` returns presigned PUT URL with `s3.amazonaws.com` host
- [ ] `GET /images/{id}` returns CDN URL when `S3_PUBLIC_URL` set; presigned GET otherwise
- [ ] `DELETE /images/{id}` removes object from S3 bucket
- [ ] Worker uploads generated PNG via `S3Storage.upload_file`; no boto3 import remains in `worker/processor.py`
- [ ] `STORAGE_PROVIDER=r2` still works end-to-end (regression)
- [ ] Structured logs include `bucket`, `region`, `storage_key`; never include credentials
- [ ] OTel spans emitted for all AWS-calling operations
- [ ] `pytest` exits 0; coverage ≥ 85%
- [ ] `.env.foreman.example` documents all `S3_*` variables
