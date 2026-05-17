# API Contracts: Completion Test UI

**Phase**: 1 (Design - API Integration)  
**Date**: 2026-05-13  
**Purpose**: Define UI expectations for foreman API endpoints; document request/response contracts

## Overview

The UI is a thin client for the foreman API. It calls **16 endpoints** documented below, including a two-step image upload flow (presigned intent + direct-to-storage PUT). All foreman requests include the `x-user-id` header. All responses are JSON; errors use standard HTTP status codes (4xx client, 5xx server).

> **Important — Upload ordering**: A project MUST have `original_image_url` set before the first generation can be submitted. The upload flow is: `POST /v1/projects/{id}/images` → PUT file to presigned URL → `GET /v1/images/{image_id}` (to get signed download URL) → `PATCH /v1/projects/{id}` (to set `original_image_url`). Only then should generation be attempted.

## Authentication & Headers

### Required Header
```
x-user-id: <UUID>  # User ID from successful /v1/users/ POST or manual entry
```

All endpoints in this contract MUST include this header. If missing, API returns 422.

---

## Endpoints Used by UI

### 1. Health Check (Discovery)

**Purpose**: Verify foreman API is reachable; used for API endpoint discovery

**Request**:
```
GET /health HTTP/1.1
Host: localhost:8000
```

**Response (200 OK)**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "service": "foreman"
}
```

**Response (Connection Refused)**:
- Timeout or no server listening
- UI falls back to dynamic discovery or manual URL override

**UI Usage**: Called on app init to confirm API availability

---

### 2. Create User

**Purpose**: Allow developers to create test users without manual API calls

**Request**:
```
POST /v1/users/ HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "email": "dev@example.com",
  "full_name": "Developer Name"
}
```

**Response (201 Created)**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "dev@example.com",
  "full_name": "Developer Name",
  "is_active": true,
  "created_at": "2026-05-13T10:30:00Z"
}
```

**Response (422 Validation Error)**:
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

**UI Usage**: Called from user creation form; stores returned `id` as x-user-id; auto-fills email/name for reference

---

### 3. Get Current User

**Purpose**: Retrieve authenticated user's profile

**Request**:
```
GET /v1/users/me HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
```

**Response (200 OK)**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "dev@example.com",
  "full_name": "Developer Name",
  "is_active": true,
  "created_at": "2026-05-13T10:30:00Z"
}
```

**Response (422 Missing Header)**:
```
422 Unprocessable Entity
[No x-user-id or invalid value]
```

**UI Usage**: Called on app init to verify x-user-id is valid; displays user name in UI header

---

### 4. List Projects

**Purpose**: Show all projects owned by current user

**Request**:
```
GET /v1/projects/?limit=20&offset=0 HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
```

**Response (200 OK)**:
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "My Test Project",
    "original_image_url": "https://example.com/image.jpg",
    "room_analysis": null,
    "created_at": "2026-05-13T10:30:00Z",
    "updated_at": "2026-05-13T10:30:00Z"
  }
]
```

**UI Expectation**: Array of ProjectRead objects; empty if no projects

**UI Usage**: Projects list view; create project form pre-populates with first project

---

### 5. Create Project

**Purpose**: Create a new project container for generations

**Request**:
```
POST /v1/projects/ HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json

{
  "name": "My New Project",
  "original_image_url": "https://example.com/input.jpg"
}
```

**Response (201 Created)**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "My New Project",
  "original_image_url": "https://example.com/input.jpg",
  "room_analysis": null,
  "created_at": "2026-05-13T10:35:00Z",
  "updated_at": "2026-05-13T10:35:00Z"
}
```

**UI Usage**: Called from project creation form; returns new project object; UI adds to projects list and selects it

---

### 6. Create Image Upload Intent

**Purpose**: Request a presigned URL for uploading a test image directly to object storage

**Request**:
```
POST /v1/projects/{project_id}/images HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json

{
  "filename": "room-photo.jpg",
  "content_type": "image/jpeg",
  "size_bytes": 2048000
}
```

**Validation**: `content_type` must match `^image/(jpeg|png|gif|webp)$`; `size_bytes` must be > 0

**Response (201 Created)**:
```json
{
  "upload_url": "https://storage.example.com/presigned-upload-url?X-Amz-Signature=...",
  "image_id": "550e8400-e29b-41d4-a716-446655440006",
  "file_key": "uploads/proj-xxx/room-photo.jpg",
  "expires_at": "2026-05-13T10:50:00Z"
}
```

**UI Expectation**: The `upload_url` is used for a direct PUT (not via foreman); check `expires_at` before PUT — if expired, call this endpoint again to get a fresh URL

**UI Usage**: Called from image upload component; stores `intent` in state; initiates browser PUT to `upload_url`

---

### 6b. Upload File to Storage (direct PUT — NOT a foreman endpoint)

**Purpose**: Upload the actual file bytes directly to storage (S3/R2) using the presigned URL

**Request** (to `upload_url` from above — NOT `localhost:8000`):
```
PUT {upload_url} HTTP/1.1
Content-Type: image/jpeg
Content-Length: 2048000

[binary file data]
```

**Response (200 OK or 204 No Content)**:
Empty body on success

**Response (403 Forbidden)**:
Presigned URL has expired; request a new upload intent

**CORS requirement**: The storage bucket (S3/R2) MUST have CORS configured to allow PUT from the UI origin (`http://localhost:3000`). Without this, the browser will block the upload. Add to bucket CORS policy:
```json
{
  "AllowedOrigins": ["http://localhost:3000"],
  "AllowedMethods": ["PUT"],
  "AllowedHeaders": ["Content-Type", "Content-Length"]
}
```

**UI Usage**: Called by `image-upload.js` via `fetch(uploadUrl, { method: 'PUT', body: file })`; track progress via `XMLHttpRequest.upload.onprogress`

---

### 6c. Get Image (post-upload signed URL retrieval)

**Purpose**: Retrieve the signed download URL for an uploaded image; use this URL to PATCH the project's `original_image_url`

**Request**:
```
GET /v1/images/{image_id} HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
```

**Response (200 OK)**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440006",
  "project_id": "550e8400-e29b-41d4-a716-446655440001",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "room-photo.jpg",
  "content_type": "image/jpeg",
  "size_bytes": 2048000,
  "storage_key": "uploads/proj-xxx/room-photo.jpg",
  "url": "https://storage.example.com/uploads/room-photo.jpg?X-Amz-Signature=...",
  "created_at": "2026-05-13T10:30:00Z",
  "updated_at": "2026-05-13T10:30:00Z"
}
```

**UI Usage**: Called immediately after successful PUT; `url` field is passed to `PATCH /v1/projects/{id}` to set `original_image_url`

---

### 6d. List Project Images

**Purpose**: List all uploaded images for a project; used to populate image picker in generation form

**Request**:
```
GET /v1/projects/{project_id}/images?limit=20&offset=0 HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
```

**Response (200 OK)**:
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440006",
    "project_id": "550e8400-e29b-41d4-a716-446655440001",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "filename": "room-photo.jpg",
    "content_type": "image/jpeg",
    "size_bytes": 2048000,
    "storage_key": "uploads/proj-xxx/room-photo.jpg",
    "url": "https://storage.example.com/uploads/room-photo.jpg?token=...",
    "created_at": "2026-05-13T10:30:00Z",
    "updated_at": "2026-05-13T10:30:00Z"
  }
]
```

**UI Usage**: Called when opening image-upload view or generation form; populates image gallery/picker; allows reusing previously uploaded images

---

### 6e. Update Project (PATCH — set original_image_url after upload)

**Purpose**: Link an uploaded image to a project as its `original_image_url`; required before first generation

**Request**:
```
PATCH /v1/projects/{project_id} HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json

{
  "original_image_url": "https://storage.example.com/uploads/room-photo.jpg?token=..."
}
```

**Response (200 OK)**:
Returns updated `ProjectRead` with `original_image_url` set

**UI Usage**: Called automatically after successful upload + image URL retrieval; updates project in state; enables generation form submit button

---

### 7. Get Styles

**Purpose**: Fetch available design styles for generation form dropdown

**Request**:
```
GET /v1/styles/?limit=100&offset=0 HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
```

**Response (200 OK)**:
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440004",
    "name": "Modern Minimalist",
    "description": "Clean lines, neutral colors, minimal ornamentation",
    "example_image_url": "https://example.com/style-modern.jpg",
    "created_at": "2026-05-13T10:00:00Z",
    "updated_at": "2026-05-13T10:00:00Z"
  },
  {
    "id": "550e8400-e29b-41d4-a716-446655440005",
    "name": "Bohemian",
    "description": "Eclectic, artistic, layered textures",
    "example_image_url": "https://example.com/style-bohemian.jpg",
    "created_at": "2026-05-13T10:00:00Z",
    "updated_at": "2026-05-13T10:00:00Z"
  }
]
```

**UI Expectation**: Array of StyleRead objects; may be empty if no styles configured

**UI Usage**: Called on app init; populates style dropdown in generation form; caches in state

---

### 7. Create Generation (Job)

**Purpose**: Submit a new image generation request

**Request**:
```
POST /v1/projects/{project_id}/generations HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json

{
  "prompt": "Modern minimalist interior design",
  "style_id": "550e8400-e29b-41d4-a716-446655440004",
  "parent_id": null,
  "model_used": null,
  "attempt": 1
}
```

**Response (202 Accepted)**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "project_id": "550e8400-e29b-41d4-a716-446655440001",
  "parent_id": null,
  "status": "pending",
  "prompt": "Modern minimalist interior design",
  "style_id": "550e8400-e29b-41d4-a716-446655440004",
  "model_used": null,
  "input_image_url": "https://storage.example.com/input-xyz.jpg",
  "output_image_url": null,
  "error_message": null,
  "processing_time_ms": null,
  "attempt": 1,
  "metadata": null,
  "created_at": "2026-05-13T10:35:00Z",
  "updated_at": "2026-05-13T10:35:00Z"
}
```

**UI Expectation**: 202 response (not 201) to indicate async job; generation has status "pending"

**UI Usage**: Called from generation form; stores returned generation ID; navigates to job detail view; starts polling

---

### 8. Get Generation

**Purpose**: Fetch current state of a specific generation job (for polling)

**Request**:
```
GET /v1/generations/{generation_id} HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
```

**Response (200 OK)**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "project_id": "550e8400-e29b-41d4-a716-446655440001",
  "parent_id": null,
  "status": "completed",
  "prompt": "Modern minimalist interior design",
  "style_id": "550e8400-e29b-41d4-a716-446655440004",
  "model_used": "stable-diffusion-v3",
  "input_image_url": "https://storage.example.com/input-xyz.jpg",
  "output_image_url": "https://storage.example.com/output-abc123.jpg",
  "error_message": null,
  "processing_time_ms": 25000,
  "attempt": 1,
  "metadata": { "seed": "12345" },
  "created_at": "2026-05-13T10:35:00Z",
  "updated_at": "2026-05-13T10:37:30Z"
}
```

**UI Expectation**: Full GenerationRead with current status; output_image_url is populated if completed

**UI Usage**: Called repeatedly (polling) from job detail view every N seconds; updates UI state; stops polling when status is terminal (completed/failed/cancelled)

---

### 9. List Generations

**Purpose**: Show all generations in current project (or all user generations)

**Request**:
```
GET /v1/projects/{project_id}/generations?limit=20&offset=0 HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
```

**Response (200 OK)**:
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440002",
    "project_id": "550e8400-e29b-41d4-a716-446655440001",
    "parent_id": null,
    "status": "completed",
    "prompt": "Modern minimalist interior design",
    "style_id": "550e8400-e29b-41d4-a716-446655440004",
    "model_used": "stable-diffusion-v3",
    "input_image_url": "https://storage.example.com/input-xyz.jpg",
    "output_image_url": "https://storage.example.com/output-abc123.jpg",
    "error_message": null,
    "processing_time_ms": 25000,
    "attempt": 1,
    "metadata": null,
    "created_at": "2026-05-13T10:35:00Z",
    "updated_at": "2026-05-13T10:37:30Z"
  }
]
```

**UI Usage**: Called from job list view; populates generation list with pagination

---

### 10. Cancel Generation

**Purpose**: Cancel a pending or processing generation

**Request**:
```
POST /v1/generations/{generation_id}/cancel HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
```

**Response (200 OK)**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "status": "cancelled",
  "...": "... other fields unchanged ..."
}
```

**Response (422 / Conflict)**:
If generation is already completed/failed, returns error

**UI Usage**: Called from job detail view cancel button; updates job status to "cancelled"

---

### 11. Retry Generation

**Purpose**: Create a new generation with same inputs as a failed one

**Request**:
```
POST /v1/generations/{generation_id}/retry HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
```

**Response (201 Created)**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440010",
  "project_id": "550e8400-e29b-41d4-a716-446655440001",
  "parent_id": "550e8400-e29b-41d4-a716-446655440002",
  "status": "pending",
  "prompt": "Modern minimalist interior design",
  "style_id": "550e8400-e29b-41d4-a716-446655440004",
  "model_used": null,
  "input_image_url": "https://storage.example.com/input-xyz.jpg",
  "output_image_url": null,
  "error_message": null,
  "processing_time_ms": null,
  "attempt": 2,
  "metadata": null,
  "created_at": "2026-05-13T10:40:00Z",
  "updated_at": "2026-05-13T10:40:00Z"
}
```

**UI Expectation**: New generation returned with attempt incremented; parent_id set to original job

**UI Usage**: Called from job detail view retry button; navigates to new generation detail view

---

### 12. Fork Generation

**Purpose**: Create a child generation using completed generation's output as input

**Request**:
```
POST /v1/generations/{generation_id}/fork HTTP/1.1
Host: localhost:8000
x-user-id: 550e8400-e29b-41d4-a716-446655440000
```

**Response (201 Created)**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440011",
  "project_id": "550e8400-e29b-41d4-a716-446655440001",
  "parent_id": "550e8400-e29b-41d4-a716-446655440002",
  "status": "pending",
  "prompt": null,  // or pre-set based on parent
  "style_id": null,
  "model_used": null,
  "input_image_url": "https://storage.example.com/output-abc123.jpg",  // parent's output
  "output_image_url": null,
  "error_message": null,
  "processing_time_ms": null,
  "attempt": 1,
  "metadata": null,
  "created_at": "2026-05-13T10:42:00Z",
  "updated_at": "2026-05-13T10:42:00Z"
}
```

**UI Expectation**: New generation with parent_id set to original; input_image_url is parent's output_image_url

**UI Usage**: Called from job detail view fork button; navigates to generation form with input pre-selected; developer can then enter new prompt/style and submit

---

## Error Response Format

All errors follow this schema:

```json
{
  "detail": "Error message" | [ { "loc": [...], "msg": "...", "type": "..." } ]
}
```

**Common Status Codes**:
- `422 Unprocessable Entity`: Validation error (missing required fields, invalid format)
- `404 Not Found`: Resource doesn't exist (project/generation not found)
- `500 Internal Server Error`: Server error; user should see "Server error, please try again"
- `Connection refused / Timeout`: Network error; UI should suggest checking if foreman is running

**UI Handler**:
All API calls catch errors and surface user-friendly messages in the notification/toast area.

---

## Polling Behavior

**Polling Loop** (in job detail view):
1. GET /v1/generations/{id}
2. If status is terminal (completed/failed/cancelled), stop polling
3. If status is non-terminal, wait pollingIntervalMs (default 3 seconds), go to step 1
4. User can manually click refresh button to fetch immediately

**Pause Conditions**:
- Tab is hidden (use `document.hidden` event)
- Window loses focus (use `blur` event)
- Resume on `show` or `focus`

---

## Expected API Behavior (for test expectations)

| Scenario | Expected Status | Expected Behavior |
|----------|-----------------|-------------------|
| Create user with valid email | 201 | User created; ID returned |
| Create user with invalid email | 422 | Validation error returned |
| Get nonexistent project | 404 | "Not found" error |
| Get generation while processing | 200 | status="processing", output_image_url=null |
| Get completed generation | 200 | status="completed", output_image_url set |
| Fork failed generation | 422 or error | Should not allow forking failed jobs |
| Cancel already-completed job | 422 or error | Should not allow cancelling completed jobs |
| Upload intent with unsupported content_type | 422 | Validation error returned |
| Upload intent with expired URL then PUT | 403 from storage | UI must request fresh intent |
| GET project images when none uploaded | 200 | Empty array returned |
| Create generation without project original_image_url | Error | Worker will fail; UI should warn before submit |
| Storage bucket missing CORS | Browser CORS error | Upload blocked; inform user to configure CORS |
