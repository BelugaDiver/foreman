# Feature Specification: Amazon S3 Image Storage Provider

**Feature Branch**: `s3-image-storage`
**Created**: 2025-07-18
**Status**: Draft
**Input**: "I want to use Amazon S3 to store my image files - this will be faster than getting started with Cloudflare. Can you spec out adding an image provider for S3?"

---

## Context

Foreman already has a `StorageProtocol` abstraction (`foreman/storage/protocol.py`) that defines three operations — `create_upload_url`, `get_download_url`, and `delete` — and a working Cloudflare R2 implementation that is the current default. `S3Settings` already exists in `foreman/storage/settings.py` but has no corresponding `S3Storage` class, and the factory does not yet handle `STORAGE_PROVIDER=s3`. Additionally, the worker's `JobProcessor._upload_to_storage` method bypasses `StorageProtocol` entirely by constructing a raw boto3 client — this is a latent defect that this feature MUST correct so the worker participates in the same provider-agnostic pattern as the API.

---

## Goals

- Allow operators to point Foreman at an Amazon S3 bucket instead of Cloudflare R2 by setting a single environment variable (`STORAGE_PROVIDER=s3`).
- Deliver all three storage operations (`create_upload_url`, `get_download_url`, `delete`) through the existing `StorageProtocol` interface with no changes to call sites in the API or worker.
- Correct the worker's direct-boto3 upload so that it routes through `StorageProtocol`, eliminating the duplicate credential-management and provider-coupling code.
- Maintain full parity in observability (structured logging, OpenTelemetry spans) and security controls (credentials from environment, presigned URL expiry) between S3 and R2 providers.

## Non-Goals

- Migrating existing images stored in R2 to S3.
- Supporting cross-provider replication or dual-write.
- Adding support for other S3-compatible providers (MinIO, DigitalOcean Spaces) — those may be added later without spec changes.
- Implementing bucket creation, lifecycle policies, or CORS configuration from within Foreman code (these are infrastructure-level concerns handled in Terraform).
- Adding a CloudFront CDN integration (out of scope for this feature; covered by the existing `S3_PUBLIC_URL` env var if an operator configures it manually).

---

## User Scenarios & Testing

### User Story 1 — Operator switches provider from R2 to S3 (Priority: P1)

An operator deploying Foreman changes `STORAGE_PROVIDER` from `r2` to `s3`, sets the four required `S3_*` environment variables, and restarts the service. No code changes are made. All subsequent upload-intent requests, download-URL requests, and delete operations go to the configured S3 bucket. The worker also uploads generated images to S3.

**Why this priority**: This is the entire reason for the feature. Everything else supports this outcome.

**Independent Test**: Can be fully tested by pointing a staging environment at a real or mock S3 bucket with `STORAGE_PROVIDER=s3` and running the existing image lifecycle (create upload intent → confirm upload → retrieve download URL → delete). Delivers a working alternative storage backend.

**Acceptance Scenarios**:

1. **Given** `STORAGE_PROVIDER=s3` and valid `S3_*` environment variables, **When** the Foreman API starts, **Then** `get_storage()` returns an `S3Storage` instance and no errors are logged at startup.
2. **Given** a running API with `STORAGE_PROVIDER=s3`, **When** a client calls `POST /projects/{project_id}/images`, **Then** the response contains a presigned `PUT` URL pointing to an `s3.amazonaws.com` (or regional) endpoint and a `file_key` following the `projects/{project_id}/{uuid}/{filename}` pattern.
3. **Given** a running API with `STORAGE_PROVIDER=s3`, **When** a client calls `GET /images/{image_id}`, **Then** the response contains a presigned `GET` URL (or public URL if `S3_PUBLIC_URL` is set) that is valid for at least 55 minutes from the time of the request.
4. **Given** a running API with `STORAGE_PROVIDER=s3`, **When** a client calls `DELETE /images/{image_id}`, **Then** the object is removed from the S3 bucket and the image record is removed from the database.
5. **Given** `STORAGE_PROVIDER=s3` and valid `S3_*` environment variables in the worker, **When** the worker finishes generating an image, **Then** the generated PNG is uploaded to S3 via `StorageProtocol` and the resulting URL is stored on the generation record.

---

### User Story 2 — Operator uses a CloudFront (or other CDN) public URL (Priority: P2)

An operator sets `S3_PUBLIC_URL=https://cdn.example.com` in addition to the required `S3_*` variables. Download URLs returned by the API use the public CDN base URL rather than a presigned S3 URL.

**Why this priority**: Presigned URLs expose the underlying S3 host and expire; a CDN URL is stable, faster to serve, and avoids AWS request costs for reads. Production deployments will almost always use this path.

**Independent Test**: Can be tested in isolation by constructing an `S3Storage` with `S3Settings(public_url="https://cdn.example.com", ...)` and asserting `get_download_url("path/to/file.jpg")` returns `https://cdn.example.com/path/to/file.jpg` without calling boto3.

**Acceptance Scenarios**:

1. **Given** `S3_PUBLIC_URL=https://cdn.example.com`, **When** `get_download_url("path/to/file.jpg")` is called, **Then** the returned URL is `https://cdn.example.com/path/to/file.jpg` and no presigned-URL generation call is made to AWS.
2. **Given** `S3_PUBLIC_URL` is not set, **When** `get_download_url` is called, **Then** a presigned `GET` URL is generated with a 1-hour expiry.

---

### User Story 3 — Misconfigured S3 environment fails loudly at startup (Priority: P2)

An operator omits one or more of the required `S3_*` environment variables. The storage layer raises a clear `ValueError` describing what is missing the first time an operation is attempted. The API continues to start (consistent with R2 behaviour) but logs a startup warning.

**Why this priority**: Operator error is the most common cause of silent failures. A clear, early message reduces time-to-diagnose from hours to seconds.

**Independent Test**: Unit-testable in isolation: construct `S3Storage` with a partially filled `S3Settings`, call any operation method, and assert `ValueError` with a meaningful message.

**Acceptance Scenarios**:

1. **Given** `S3_ACCESS_KEY_ID` is missing from the environment, **When** `S3Settings.from_env()` is called, **Then** `is_configured` returns `False`.
2. **Given** `S3Settings.is_configured == False`, **When** any storage operation is attempted, **Then** a `ValueError` is raised with a message identifying the missing configuration and the expected env var names.
3. **Given** an unconfigured S3 storage backend, **When** the Foreman API starts, **Then** a `WARNING`-level structured log entry is emitted noting that S3 storage is not configured.

---

### User Story 4 — Worker uses StorageProtocol, not raw boto3 (Priority: P1)

The worker's `JobProcessor._upload_to_storage` is refactored to inject a `StorageProtocol` instance and call `create_upload_url` / direct upload via the protocol, rather than constructing a boto3 client inline. The worker config gains S3-specific settings and loses the duplicate R2 credentials it currently carries for upload.

**Why this priority**: The bypass is an architectural violation of Constitution Principle V and prevents the worker from benefiting from provider switching. Fixing it is a prerequisite for S3 support in the worker.

**Independent Test**: Can be tested by mocking a `StorageProtocol` and asserting the worker calls the protocol methods rather than boto3 directly. No real AWS or R2 credentials required.

**Acceptance Scenarios**:

1. **Given** `STORAGE_PROVIDER=s3` in the worker environment, **When** a generation job completes, **Then** the generated image is uploaded using `S3Storage.create_upload_url` or a direct-upload variant via the protocol — no raw boto3 client is constructed in the processor.
2. **Given** `STORAGE_PROVIDER=r2` in the worker environment, **When** a generation job completes, **Then** the upload still works via `R2Storage` through the protocol (regression test).
3. **Given** the storage protocol raises an exception during upload, **When** the worker processes a job, **Then** the exception propagates and the generation is marked `failed` with an appropriate error message.

---

### Edge Cases

- What happens when the S3 bucket does not exist or the credentials lack `s3:PutObject` permission? → `S3Storage` must surface the underlying `ClientError` without swallowing it; the worker's retry mechanism handles transient failures.
- What happens when `delete` is called for a `storage_key` that no longer exists in S3? → Return `False` and log a warning (consistent with R2 behaviour); do not raise.
- What happens when the presigned URL expires before the client uses it? → This is a client concern; Foreman's responsibility is to set a minimum 1-hour expiry window and document it.
- What key path format does S3 use compared to R2? → Identical: `projects/{project_id}/{uuid}/{filename}` for user uploads, `generations/{uuid}.png` for worker-produced images.
- What if both `STORAGE_PROVIDER=s3` and R2 env vars are set? → Only the provider matching `STORAGE_PROVIDER` is initialised; unrelated env vars are ignored.

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST support `STORAGE_PROVIDER=s3` as a valid value for the `STORAGE_PROVIDER` environment variable, causing `get_storage()` to return an `S3Storage` instance.
- **FR-002**: `S3Storage` MUST implement all three methods of `StorageProtocol` — `create_upload_url`, `get_download_url`, and `delete` — with identical signatures and return types.
- **FR-003**: `S3Storage.create_upload_url` MUST generate a presigned `PUT` URL scoped to a single object key following the pattern `projects/{project_id}/{uuid}/{filename}`, expiring in no less than 1 hour.
- **FR-004**: `S3Storage.get_download_url` MUST return `{S3_PUBLIC_URL}/{storage_key}` when `S3_PUBLIC_URL` is configured, and a presigned `GET` URL (expiring in no less than 1 hour) when it is not.
- **FR-005**: `S3Storage.delete` MUST attempt to remove the object from the bucket, return `True` on success, and return `False` (without raising) on failure, logging the error at `ERROR` level.
- **FR-006**: `S3Storage` MUST wrap all blocking boto3 calls with `asyncio.to_thread()` to comply with Constitution Principle III (Async-First).
- **FR-007**: `S3Storage` MUST emit a structured `INFO` log on successful initialisation and a `WARNING` log when initialised without complete credentials.
- **FR-008**: Every `S3Storage` operation that calls AWS MUST be wrapped in an OpenTelemetry span recording `storage_key`, `bucket`, and outcome attributes.
- **FR-009**: The storage factory MUST clear its `lru_cache` after any configuration change (operators must restart the service to switch providers — this is the existing documented behaviour; no new behaviour is required).
- **FR-010**: `S3Settings.from_env()` MUST read `S3_BUCKET`, `S3_REGION` (default `us-east-1`), `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, and `S3_PUBLIC_URL` from environment variables. (`S3Settings` already exists; this requirement confirms its contract.)
- **FR-011**: `S3Settings.is_configured` MUST return `True` only when both `access_key_id` and `secret_access_key` are non-empty. (If neither is set, the implementation SHOULD attempt IAM role-based credentials via boto3's default credential chain — see Assumptions.)
- **FR-012**: The worker's `JobProcessor._upload_to_storage` MUST be refactored to accept a `StorageProtocol` instance and use it for all storage operations, removing the inline boto3 client construction.
- **FR-013**: `WorkerConfig` MUST expose the S3 configuration variables (`S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`) needed to initialise `S3Storage` in the worker process. (Existing `aws_access_key_id` / `aws_secret_access_key` / `aws_region` fields may be reused or superseded — see Assumptions.)
- **FR-014**: The example environment file (`.env.foreman.example`) MUST include a commented S3 configuration block documenting all required and optional `S3_*` variables.

### Key Entities

- **S3Storage**: A concrete implementation of `StorageProtocol` backed by Amazon S3. Stateless beyond the boto3 client it holds; created once at startup via the factory and reused for all requests.
- **S3Settings**: Configuration dataclass (already partially exists) holding bucket name, region, access credentials, and optional public CDN URL. Constructed from environment variables via `from_env()`.
- **UploadIntent**: Unchanged existing dataclass — `upload_url`, `file_key`, `expires_at`. Returned by `create_upload_url`.
- **StorageProtocol**: Unchanged existing ABC. `S3Storage` adds a second concrete implementation alongside the existing `R2Storage`.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Switching from `STORAGE_PROVIDER=r2` to `STORAGE_PROVIDER=s3` requires no application code changes — only environment variable updates and a service restart.
- **SC-002**: An end-to-end image lifecycle (upload intent → confirm upload → retrieve → delete) completes successfully against a real S3 bucket in under 5 seconds (excluding the client's direct upload time, which is network-dependent).
- **SC-003**: All existing unit and integration tests continue to pass after the changes (`pytest` exits with code 0, coverage gate ≥ 85% maintained).
- **SC-004**: New unit tests cover 100% of `S3Storage` method paths, including success, misconfiguration, and AWS error branches.
- **SC-005**: The worker's `_upload_to_storage` refactor results in zero direct boto3 imports remaining in `worker/processor.py`.
- **SC-006**: A developer reviewing the codebase can identify the S3 provider and all its configuration variables within 5 minutes using only the README and `.env.foreman.example`.

---

## Assumptions

- **Credential strategy**: If neither `S3_ACCESS_KEY_ID` nor `S3_SECRET_ACCESS_KEY` is set, the implementation will delegate to boto3's default credential chain (IAM roles, `~/.aws/credentials`, EC2 instance profiles). This allows deployment on AWS infrastructure without storing long-lived keys. The `is_configured` property will return `True` in this case, trusting boto3 to resolve credentials at call time.
- **boto3 already installed**: The project already uses `boto3` for R2 and SQS. No new dependencies are introduced.
- **Region defaults to `us-east-1`**: If `S3_REGION` is not set, the S3 client will target `us-east-1`. Operators in other regions must set `S3_REGION` explicitly to avoid cross-region latency.
- **Worker key naming convention for generated images**: The worker uses `generations/{uuid}.png` as the storage key for AI-generated images. This convention is preserved unchanged; only the client construction is refactored.
- **No path-style URLs**: Standard virtual-hosted-style S3 URLs are used (`https://{bucket}.s3.{region}.amazonaws.com/{key}`). Operators requiring path-style (e.g., legacy setups) are out of scope.
- **WorkerConfig S3 vs AWS fields**: `WorkerConfig` already has `aws_access_key_id`, `aws_secret_access_key`, and `aws_region`. These fields will be mapped to S3 credentials in the worker (via `S3Settings.from_env()`) rather than adding duplicate `s3_*` fields, keeping the worker config consistent with the already-established naming for SQS.
- **Presigned URL expiry**: 1-hour presigned URLs are sufficient for both upload intents and download links, consistent with the current R2 behaviour.
- **No server-side encryption config**: Default AWS S3 server-side encryption (SSE-S3) via bucket policy is assumed to be configured at the infrastructure level. The `S3Storage` implementation will not pass explicit SSE headers.

---

## Security Considerations

*(Anchored to Constitution Principle VIII)*

- **Credentials from environment only**: `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` MUST be read exclusively from environment variables. They MUST NOT appear in source code, config files committed to version control, or logs.
- **Presigned URL expiry**: All presigned URLs (upload and download) MUST carry an explicit expiry of 1 hour. Expired URLs return HTTP 403 from AWS — clients must request a new URL from the Foreman API.
- **Least-privilege IAM policy**: The IAM user or role whose credentials are supplied MUST have only `s3:PutObject`, `s3:GetObject`, and `s3:DeleteObject` on the specific bucket. `s3:ListBucket` and `s3:*` MUST be withheld. (This is an infrastructure/deployment requirement documented in the README, not enforced by application code.)
- **SSRF protection in worker**: When the worker uploads generated images, the resulting S3 URL MUST be added to `WorkerConfig.get_allowed_image_domains()` so that if the URL is later used as an input image URL, it passes the SSRF allowlist check. The existing allowlist mechanism is reused; only the domain extraction logic needs updating to also parse `S3_PUBLIC_URL` and the S3 bucket hostname.
- **No credential logging**: `S3_SECRET_ACCESS_KEY` and `S3_ACCESS_KEY_ID` MUST NOT appear in any log record. The structured logger MUST only record the bucket name, region, and file key.
- **Content-Type enforcement**: Presigned `PUT` URLs for user uploads MUST bind the `Content-Type` header to the value provided at intent creation time. This prevents a client from uploading a different content type (e.g., an executable) under the cover of an image intent.

---

## Open Questions

1. **Worker storage injection pattern**: The simplest refactor of `_upload_to_storage` passes a `StorageProtocol` via `JobProcessor.__init__`. However, `worker/agent.py` or `worker/main.py` constructs `JobProcessor` and would need to call `get_storage()`. Is it acceptable to call the storage factory in the worker's bootstrap path, or does the worker need its own factory distinct from the API's? *(Assumption: the worker can safely call the shared factory; the `lru_cache` makes it cost-free.)*

2. **Direct upload vs. presigned-URL-and-confirm flow for worker**: The worker uploads a local file directly (it has the bytes). `StorageProtocol.create_upload_url` returns a presigned URL intended for a browser client to PUT to. The worker would need to either (a) perform an `asyncio.to_thread(client.upload_fileobj, ...)` call directly, or (b) treat `file_key` from `create_upload_url` as the target key and upload via the boto3 client separately. Should `StorageProtocol` gain a `upload_file(path, key)` method for the worker path, or should the worker call `create_upload_url` solely to obtain a `file_key` and then upload using internal means? *(This is the most significant design question for the worker refactor.)*

3. **WorkerConfig credential field consolidation**: `WorkerConfig` currently has `aws_access_key_id`, `aws_secret_access_key`, `aws_region` (used for SQS) and `r2_access_key_id`, `r2_secret_access_key` (used for R2). Adding S3 would introduce a third credential set unless we unify. Should S3 in the worker reuse the `aws_*` fields (implying SQS and S3 share credentials), or should dedicated `s3_*` fields be added for orthogonality?
