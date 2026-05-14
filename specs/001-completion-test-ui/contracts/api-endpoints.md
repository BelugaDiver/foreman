# API Contracts: Completion Test UI

**Phase**: 1 (Design - API Integration)  
**Date**: 2026-05-13  
**Purpose**: Define UI expectations for foreman API endpoints; document request/response contracts

## Overview

The UI is a thin client for the foreman API. It calls exactly 13 endpoints, documented below. All requests include the `x-user-id` header. All responses are JSON; errors use standard HTTP status codes (4xx client, 5xx server).

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

### 6. Get Styles

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
| API unreachable | Connection error | Timeout; UI suggests checking foreman running |
