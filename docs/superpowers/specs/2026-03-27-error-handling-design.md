# Error Handling Design

**Date:** 2026-03-27  
**Status:** Draft  
**Author:** opencode

## Goal

Implement a hybrid error handling approach that provides actionable error messages to API clients while centralizing infrastructure error handling.

## Problem Statement

Currently, all database and storage errors are caught with generic `except Exception` blocks and returned as 500 Internal Server Errors. This provides no actionable guidance to clients about whether to retry, fix their request, or wait.

## Design

### Architecture

Two-layer error handling:

1. **Centralized handlers** (main.py) - Infrastructure errors (DB connection, timeouts, storage)
2. **Per-endpoint handling** - Domain errors (not found, duplicates, invalid state)

### Layer 1: Infrastructure Errors (Centralized)

Add exception handlers in `main.py` for common infrastructure exceptions:

| Exception | HTTP Status | Message |
|-----------|-------------|---------|
| `asyncpg.ConnectionFailure` | 503 | "Database temporarily unavailable" |
| `asyncpg.QueryCanceledError` | 503 | "Database temporarily unavailable" |
| `asyncio.TimeoutError` | 503 | "Service temporarily unavailable" |
| Storage timeout/connection | 503 | "Storage service temporarily unavailable" |

### Layer 2: Domain Errors (Per-endpoint)

Create custom domain exceptions in `foreman/exceptions.py`:

```python
class ResourceNotFoundError(Exception):
    """Raised when a resource doesn't exist or user doesn't have access."""
    pass

class DuplicateResourceError(Exception):
    """Raised when creating a resource that already exists."""
    pass

class InvalidStateError(Exception):
    """Raised when operation can't be performed due to current state."""
    pass
```

#### Domain Error Status Codes

| Scenario | HTTP Status | Message |
|----------|-------------|---------|
| Resource not found / FK invalid | 404 | "Resource not found" |
| Duplicate resource | 400 | (Endpoint-specific) |
| Invalid state for operation | 400 | (Endpoint-specific) |
| Validation error | 422 | FastAPI auto-handles |

### Implementation Plan

1. Create `foreman/exceptions.py` with domain exceptions
2. Add exception handlers to `main.py` for infrastructure errors
3. Update repositories to raise domain exceptions instead of returning None (where appropriate)
4. Update endpoints to:
   - Remove broad `except Exception` + 500 blocks for expected errors
   - Let infrastructure errors propagate to handlers
   - Raise domain exceptions from repositories

### Files Changed

- **New:** `foreman/exceptions.py`
- **Modified:** `foreman/main.py`
- **Modified:** `foreman/api/v1/endpoints/*.py` (remove unnecessary 500 handlers)
- **Modified:** `foreman/repositories/*.py` (raise domain exceptions)

### Example Flow

```
Client POST /v1/projects/123/generations
    │
    ├─► Repository checks project exists
    │       │
    │       └─► Project not found → raise ResourceNotFoundError
    │
    ├─► Endpoint catches ResourceNotFoundError
    │       │
    │       └─► raise HTTPException(404, "Project not found")
    │
    └─► Client receives 404
```

### Alternative Considered

**Pure centralized handlers** - Would lose endpoint context for domain errors like "cannot cancel completed generation" which need specific messages.

## Testing

- Unit tests for each exception handler in main.py
- Integration tests for each endpoint error case
- Verify 503 returned for simulated DB/storage unavailability

## Success Criteria

- All current 500 errors from infrastructure failures become 503
- All domain errors return appropriate 4xx status codes
- Error messages are actionable (client knows to retry, fix input, or wait)
- No information leakage about internal errors to clients
