# Design: Non-GET Endpoint Parameter Standard

**Date:** 2026-03-25
**Status:** Approved
**Topic:** Ensure all non-GET endpoint parameters (except resource IDs) are passed in the request body.

---

## 1. Objective
Standardize how parameters are passed to `POST`, `PUT`, `PATCH`, and `DELETE` endpoints in the Foreman API. This ensures a clean separation between resource identification (via Path) and action-specific data (via Body), improving API consistency and security.

## 2. Architectural Principles
- **RESTful Path Parameters:** UUIDs and other identifiers used for resource locating (e.g., `project_id`, `generation_id`, `image_id`) remain in the URL Path.
- **Request Body for Payload:** Any data that describes the action or configures the operation must be encapsulated in a Pydantic model and passed via the Request Body.
- **Explicit Body Declaration:** Use FastAPI's `Body(...)` marker in endpoint function signatures to explicitly define parameters as body content, even if they are Pydantic models (where it's technically optional but preferred for clarity).

## 3. Implementation Details

### 3.1 Endpoint Updates
The following endpoints will be updated to use explicit `Body(...)` markers for their payload parameters:

| File | Endpoint | Parameter | Current Source | New Source |
|------|----------|-----------|----------------|------------|
| `generations.py` | `PATCH /{generation_id}` | `generation_in` | Implicit Body | Explicit `Body()` |
| `images.py` | `POST /projects/{project_id}/images` | `request` | Implicit Body | Explicit `Body()` |
| `projects.py` | `POST /` | `project_in` | Implicit Body | Explicit `Body()` |
| `projects.py` | `POST /{project_id}/generations` | `generation_in` | Implicit Body | Explicit `Body()` |
| `projects.py` | `PATCH /{project_id}` | `project_in` | Implicit Body | Explicit `Body()` |
| `users.py` | `POST /` | `user_in` | Implicit Body | Explicit `Body()` |
| `users.py` | `PATCH /me` | `user_in` | Implicit Body | Explicit `Body()` |

### 3.2 Schema Validation
- Pydantic's `extra="forbid"` configuration is already in use and will continue to be enforced to prevent unexpected fields in the request body.

## 4. Testing & Verification
- **Unit/Integration Tests:** Run `pytest` to ensure that existing tests (which already use JSON bodies) still pass.
- **OpenAPI Verification:** Check the generated `/docs` or `openapi.json` to ensure the parameter location is correctly documented as `body`.

## 5. Maintenance
Any new non-GET endpoints added to the system must follow this pattern. This will be documented in the project's `ARCHITECTURE.md` as a mandatory convention.
