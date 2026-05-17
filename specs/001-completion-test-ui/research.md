# Research: Completion Test UI

**Phase**: 0 (Research & Dependency Analysis)  
**Date**: 2026-05-13  
**Status**: Complete (no NEEDS CLARIFICATION items in specification)

## Key Decisions Finalized

### 1. API Endpoint Discovery

**Decision**: Attempt localhost:8000 first, then fallback to dynamic discovery  
**Rationale**: Localhost is the default dev environment; dynamic discovery allows flexibility for deployed instances  
**Implementation**: Fetch `http://localhost:8000/health` on app load; if fails, try `/.well-known/openapi.json` or root endpoint from same origin  
**Fallback**: Manual API URL input in settings panel

### 2. User Authentication Model

**Decision**: Support both user creation via API and manual ID entry  
**Rationale**: Allows testing with pre-existing users or fresh test accounts  
**Implementation**: 
- User creation form calls `/v1/users/` and stores returned user.id in localStorage as x-user-id
- Settings panel allows manual entry of existing user IDs
- All API requests include x-user-id header

### 3. Real Worker Requirement

**Decision**: UI assumes real workers are running; no mocking layer in UI  
**Rationale**: Focus testing tool on E2E validation, not on simulating worker behavior  
**Dependency**: Foreman worker service must be running for full feature testing  
**Implication**: If worker isn't available, jobs will stay in "pending" state; expected behavior

### 4. Deployment Model

**Decision**: Static web files served from `foreman/ui/` via simple HTTP server  
**Rationale**: Zero backend required; quick iteration; easy for developers to run  
**Command**: `cd foreman/ui && python -m http.server 3000`

### 5. Polling Strategy

**Decision**: Client-side polling with configurable interval (default 2-5 seconds)  
**Rationale**: Simpler than WebSockets for a dev tool; HTTP polling is more resilient  
**Optimization**: Only poll active job detail views; pause polling when tab is hidden  
**Fallback**: Manual refresh button always available

### 6. Frontend Library Choice

**Decision**: Vanilla JavaScript ES6+ or lightweight library (htmx/Alpine.js)  
**Rationale**: No build step; minimal dependencies; easy for contributors to understand  
**Constraint**: Total JS < 50KB uncompressed (excluding comments)

## Verified Assumptions

- ✅ Foreman API follows OpenAPI 3.1.0 spec
- ✅ All API endpoints require x-user-id header
- ✅ Output images are accessible via signed/public URLs
- ✅ Generation status transitions are: pending → processing → completed/failed/cancelled
- ✅ Parent/child generation relationships tracked via parent_id

## Dependencies & External APIs

| Service | Endpoint | Usage | Required |
|---------|----------|-------|----------|
| Foreman API | `http://localhost:8000/v1/*` | All operations | Yes |
| Foreman Health | `http://localhost:8000/health` | API discovery | No (fallback to manual) |
| Browser APIs | localStorage, fetch, EventTarget | State, HTTP, events | Yes (built-in) |

## Deliverables from Phase 0

- [x] All design decisions ratified
- [x] No blockers identified
- [x] External dependencies verified
- [x] Ready to proceed to Phase 1 design
