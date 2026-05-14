# Tasks: Completion Test UI

**Input**: Design documents from `specs/001-completion-test-ui/`
**Feature**: Standalone web UI for E2E testing of foreman image-generation pipeline
**Branch**: `001-completion-test-ui`

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: User story label (US1–US4); omitted for Setup, Foundational, and Polish phases
- All paths are relative to the repository root

---

## Phase 1: Setup

**Purpose**: Create the full file structure so all subsequent tasks have a target file to edit

- [ ] T001 Create `foreman/ui/` directory and scaffold all empty placeholder files: `index.html`, `styles.css`, `app.js`, `api.js`, `state.js`, `components/settings.js`, `components/auth.js`, `components/projects.js`, `components/image-upload.js`, `components/generation-form.js`, `components/job-list.js`, `components/job-detail.js`, `components/utils.js`, `README.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure all components share — state management, HTTP client, utilities, routing shell, and base HTML/CSS. **No user story work starts until this phase is complete.**

⚠️ **CRITICAL**: All Phase 3+ tasks depend on T002–T008

- [ ] T002 Implement `foreman/ui/state.js` — full state shape from data-model.md (user, settings, apiStatus, projects, generations, images, styles, ui, polling buckets); implement all getters, setters, event listeners (`onStateChange`), and localStorage persistence for `foremanUI::userId`, `foremanUI::apiBaseUrl`, `foremanUI::pollingInterval`, `foremanUI::lastKnownUser`
- [ ] T003 [P] Implement `foreman/ui/utils.js` — `formatDate(iso)`, `formatStatus(status)` (returns label + CSS class), `parseApiError(response)` (surfaces 422 detail arrays and 4xx/5xx messages as user-friendly strings), `createElement(tag, attrs, children)`, `isValidUuid(str)`, `isExpired(isoTimestamp)` (checks `expires_at` before upload PUT)
- [ ] T004 Implement `foreman/ui/api.js` — base `apiRequest(method, path, body)` that injects `x-user-id` header from state, handles JSON parse errors and HTTP error codes; implement named methods for all 15 foreman endpoints: `checkHealth()`, `createUser(email, fullName)`, `getUser()`, `listProjects(limit, offset)`, `createProject(name, originalImageUrl)`, `getProject(projectId)`, `updateProject(projectId, patch)`, `createUploadIntent(projectId, filename, contentType, sizeBytes)`, `getImage(imageId)`, `listImages(projectId, limit, offset)`, `listStyles(limit)`, `createGeneration(projectId, payload)`, `getGeneration(generationId)`, `listGenerations(projectId, limit, offset)`, `cancelGeneration(generationId)`, `retryGeneration(generationId)`, `forkGeneration(generationId, payload)`
- [ ] T005 Implement `foreman/ui/app.js` — `init()` function: discover API (GET `/health` → if fail, try `/.well-known/openapi.json` → fallback to manual prompt), validate x-user-id if present (call `getUser()`), load styles once, register `visibilitychange` listener to pause/resume polling; implement `switchView(viewName)` that shows the named view container and hides others; implement global notification renderer reading `state.ui.notificationQueue`
- [ ] T006 [P] Implement `foreman/ui/components/settings.js` — settings panel rendering: API base URL text input, x-user-id text input, polling interval number input; save button writes to state (and localStorage via state setters); load values from state on render; display current API discovery status
- [ ] T007 [P] Build `foreman/ui/index.html` — semantic HTML5 SPA shell: `<nav>` with links for each view (Settings, Auth, Projects, Upload, Generate, Jobs), `<main>` with one `<section id="view-*">` per view name in the `currentView` union type (`settings`, `auth`, `projects`, `image-upload`, `job-form`, `job-list`, `job-detail`), `<div id="notifications">` for toast container, `<script type="module" src="app.js">` entry point
- [ ] T008 [P] Build `foreman/ui/styles.css` — layout: CSS grid nav + main; view sections default `display:none`, active view `display:block`; forms: labelled inputs, validation error styling; buttons: primary/secondary/danger; status badges: color-coded by generation status (`pending`=yellow, `processing`=blue, `completed`=green, `failed`=red, `cancelled`=grey); image containers with `max-width:100%`; upload progress bar; notification toasts (slide-in, auto-dismiss); loading spinner

**Checkpoint**: Foundation ready — open `http://localhost:3000`, see nav and empty view containers, no console errors

---

## Phase 3: User Story 1 — Create and Submit Generation Job (Priority: P1) 🎯 MVP

**Goal**: Complete E2E workflow — register a test user → create a project → upload a test image → submit a generation job

**Independent Test**: (1) Open UI, (2) create user, (3) create project, (4) upload a JPEG, (5) fill in a prompt, (6) click Submit — verify generation created with `status: "pending"` in foreman

### Implementation for User Story 1

- [ ] T009 [P] [US1] Implement `foreman/ui/components/auth.js` — render user creation form (email + full name fields); on submit call `api.createUser()`, store returned user via `state.setUser()`, navigate to projects view; on app init call `api.getUser()` to verify existing x-user-id is valid; display "No user ID set" warning with link to auth view if unauthenticated (FR-019)
- [ ] T010 [P] [US1] Implement `foreman/ui/components/projects.js` — render project list from `state.projects.items` with project name, `original_image_url` status indicator (green check if set, amber warning if null); "New Project" form with name input (original_image_url optional at creation); on create call `api.createProject()`, add to state, select new project; "Upload Image" button navigates to `image-upload` view with current project context
- [ ] T011 [US1] Implement `foreman/ui/components/image-upload.js` — file input (`accept="image/jpeg,image/png,image/webp,image/gif"`); validate file `size ≤ 50MB` and `type` matches allowed set before API call (FR-005c); call `api.createUploadIntent()`, store intent via `state.setUploadIntent()`; check `isExpired(intent.expiresAt)` before PUT — if expired re-request intent; upload via `XMLHttpRequest` with `upload.onprogress` → `state.setUploadProgress(percent)`; on XHR success call `api.getImage(intent.imageId)` to retrieve signed URL; call `api.updateProject(projectId, { original_image_url: image.url })` to set project input; update project in state; call `state.clearUpload()`; display thumbnail on success; display project image list via `api.listImages()` with previously uploaded images (FR-005d)
- [ ] T012 [US1] Implement `foreman/ui/components/generation-form.js` — prompt `<textarea>` (required); style `<select>` populated from `state.getStyles()` (optional); if `state.getCurrentProject().originalImageUrl` is null show amber warning banner "Project has no input image — upload one before submitting" and disable submit button (FR-006); on submit call `api.createGeneration(projectId, { prompt, style_id, parent_id })` → on success call `state.setCurrentGeneration(gen.id)` and `switchView('job-detail')`

**Checkpoint US1**: Full E2E submit path works. No worker needed to verify creation — just confirm generation is created with `status: "pending"` and correct `input_image_url`

---

## Phase 4: User Story 2 — Monitor Job Completion Status (Priority: P1)

**Goal**: Watch a submitted job transition through states in real-time; see output image on completion

**Independent Test**: (1) Submit a generation, (2) observe status polling updating the view, (3) when worker completes confirm output image is displayed and `processing_time_ms` is shown

### Implementation for User Story 2

- [ ] T013 [US2] Implement `foreman/ui/components/job-detail.js` — render all generation fields: ID, status badge, prompt, style, model_used, processing_time_ms, input_image_url thumbnail, output_image_url image (shown when status `completed`), error_message paragraph (shown when `failed`), created_at / updated_at timestamps; Cancel button (enabled only when status is `pending` or `processing`) calls `api.cancelGeneration()` and updates state; wire to polling: on mount call `state.startPolling(gen.id)`; on unmount call `state.stopPolling()`
- [ ] T014 [US2] Implement `startPolling` / `stopPolling` in `foreman/ui/app.js` — `startPolling(generationId)`: set `state.polling.activeJobId`, create `setInterval` at `state.settings.pollingIntervalMs`, each tick calls `api.getGeneration(generationId)` → updates generation in state; stop when status reaches terminal state (`completed`, `failed`, `cancelled`); pause interval when `document.hidden` is true (visibilitychange); `stopPolling()`: clear interval, reset polling state

**Checkpoint US2**: Submit a job, navigate to job-detail, observe live status transitions; worker must be running to reach `completed`

---

## Phase 5: User Story 3 — Job History and Exploration (Priority: P2)

**Goal**: Browse all past generations for a project; drill into any job; retry a failed job

**Independent Test**: (1) Create several jobs across sessions, (2) open Jobs view, (3) verify paginated list shows all jobs with status/prompt preview, (4) click any job to open detail, (5) retry a failed job

### Implementation for User Story 3

- [ ] T015 [P] [US3] Implement `foreman/ui/components/job-list.js` — fetch generations via `api.listGenerations(projectId)` on view entry; render table/card list: job ID (truncated), prompt preview (first 60 chars), status badge, `created_at`; click row navigates to `job-detail` view; pagination controls (prev/next) using `limit/offset`; "New Generation" button navigates to `job-form`
- [ ] T016 [US3] Add Retry button to `foreman/ui/components/job-detail.js` — visible only when status is `failed`; calls `api.retryGeneration(generationId)`, navigates to detail view for the new generation returned by the API

**Checkpoint US3**: Job list shows all historical jobs; clicking through to details and retrying a failed job all work

---

## Phase 6: User Story 4 — Multi-Step Job Chains (Priority: P2)

**Goal**: Fork a completed generation's output as the input for a new generation; trace parent/child relationships

**Independent Test**: (1) Complete a generation, (2) click Fork, (3) verify new generation form pre-fills `parent_id`, (4) submit, (5) verify new generation's `input_image_url` matches parent's `output_image_url`

### Implementation for User Story 4

- [ ] T017 [US4] Add Fork button to `foreman/ui/components/job-detail.js` — visible only when status is `completed` and `output_image_url` is present; navigates to `job-form` view with `parent_id` pre-set in `generation-form.js`; display parent job's output image as preview in generation form
- [ ] T018 [P] [US4] Update `foreman/ui/components/job-detail.js` — show `parent_id` as a clickable link (navigates to parent job-detail when clicked); placeholder for child generations list (initially empty — can be populated via future `listGenerations` filter by `parent_id` if the API supports it)

**Checkpoint US4**: Fork chain created; parent_id visible on child; clicking parent link navigates correctly

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, error resilience, and UX completeness across all stories

- [ ] T019 [P] Create `foreman/ui/README.md` — setup steps (start foreman, `python -m http.server 3000`), CORS prerequisite for S3/R2 bucket, link to `specs/001-completion-test-ui/quickstart.md`, list of all 15 foreman endpoints the UI calls
- [ ] T020 [P] Add API discovery fallback logic to `foreman/ui/app.js` — if `GET /health` fails: try `GET /.well-known/openapi.json` (relative to origin); if both fail: show modal prompting user to enter API base URL manually (saves to localStorage); (FR-003, FR-004)
- [ ] T021 [P] Add `FR-017` error handling across all components — `parseApiError()` from utils.js must surface 422 validation detail arrays as field-level errors on forms; 4xx/5xx responses render as dismissible toast notifications via `state.addNotification()`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS all user stories**
- **Phase 3 (US1)**: Depends on Phase 2 — T009/T010 can run in parallel; T011 after T010; T012 after T011
- **Phase 4 (US2)**: Depends on Phase 2; best after Phase 3 (needs a job to poll)
- **Phase 5 (US3)**: Depends on Phase 2; can run in parallel with Phase 4
- **Phase 6 (US4)**: Depends on Phase 4 (needs job-detail.js base from T013)
- **Phase 7 (Polish)**: Depends on all desired phases being complete

### User Story Dependencies

| Story | Depends On | Can Parallel With |
|-------|-----------|-------------------|
| US1 (P1) | Phase 2 | — |
| US2 (P1) | Phase 2, Phase 3 (T013 extends job-detail started in US2) | US3 |
| US3 (P2) | Phase 2 | US2, US4 |
| US4 (P2) | US2 (T013 — job-detail base) | US3 |

### Within Each User Story

- [P] tasks within a story can be worked simultaneously (different files)
- Non-[P] tasks within a story follow sequential order (T009 → T010 → T011 → T012 for US1)
- `state.js` (T002) must be complete before any component is implemented

---

## Parallel Execution Examples

### Phase 2 Parallelism

```
T002 state.js          ← start first (others depend on this shape)
T003 utils.js [P]      ← in parallel with T002 (no state dependency)
T004 api.js            ← after T002 (reads state for x-user-id)
T005 app.js            ← after T004 (calls api)
T006 settings.js [P]   ← after T002/T004
T007 index.html [P]    ← after T005 (know all view names)
T008 styles.css [P]    ← in parallel with T007 (no JS dependency)
```

### Phase 3 (US1) Parallelism

```
T009 auth.js [P]       ← after Phase 2 complete
T010 projects.js [P]   ← after Phase 2 complete, parallel with T009
T011 image-upload.js   ← after T010 (needs project state shape)
T012 generation-form.js ← after T011 (needs upload warning logic)
```

---

## Implementation Strategy

### MVP First (US1 + US2 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002–T008) — **critical path**
3. Complete Phase 3: US1 (T009–T012)
4. Complete Phase 4: US2 (T013–T014)
5. **STOP AND VALIDATE**: Full E2E — create user → project → upload → generate → watch completion
6. Ship or continue to US3/US4

### Incremental Delivery

1. Setup + Foundational → static shell served at `localhost:3000`
2. US1 → submit generation end-to-end (MVP)
3. US2 → real-time status monitoring (full E2E confirmed)
4. US3 → job history browsing
5. US4 → fork/chain workflow
6. Polish → documentation + error resilience

---

## Task Summary

| Phase | Tasks | Count |
|-------|-------|-------|
| Phase 1: Setup | T001 | 1 |
| Phase 2: Foundational | T002–T008 | 7 |
| Phase 3: US1 (P1) — MVP | T009–T012 | 4 |
| Phase 4: US2 (P1) | T013–T014 | 2 |
| Phase 5: US3 (P2) | T015–T016 | 2 |
| Phase 6: US4 (P2) | T017–T018 | 2 |
| Phase 7: Polish | T019–T021 | 3 |
| **Total** | | **21** |

**Parallel opportunities identified**: 10 tasks marked [P] across all phases  
**MVP scope**: Phases 1–4 (15 tasks) — delivers full E2E create → submit → monitor workflow  
**Suggested start**: T001 → T002 + T003 in parallel → T004 → T005 + T006 + T007 + T008 in parallel → T009 + T010 in parallel → T011 → T012
