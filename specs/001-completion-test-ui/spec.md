# Feature Specification: Completion Test UI

**Feature Branch**: `001-completion-test-ui`  
**Created**: 2026-05-13  
**Status**: Draft  
**Input**: User description: "I need a quick, rudimentary web ui that I can use to test completion jobs originating from foreman to the worker. Can you analyze the open api spec and hook up a UI that can E2E test it all?"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create and Submit Generation Job (Priority: P1)

A developer needs to quickly verify that foreman can accept image generation requests and that workers can process them end-to-end. They need a simple interface to create a project, submit a generation job with a prompt and style, and monitor its status without writing code.

**Why this priority**: This is the core end-to-end workflow. Without the ability to create and submit jobs, there's no foundation for testing. This is the MVP.

**Independent Test**: Can be fully tested by (1) accessing the UI, (2) creating a project and generation job, (3) verifying the job is created with pending status in the system. Delivers immediate value by enabling job submission testing.

**Acceptance Scenarios**:

1. **Given** a user is on the test UI, **When** they fill in a prompt and select a style, **Then** they can click submit and a new generation job is created with status "pending"
2. **Given** a generation job has been created, **When** they view the job details, **Then** they can see the prompt, style, project ID, and current status
3. **Given** the UI is on the creation form, **When** they try to submit without filling required fields, **Then** the UI shows validation errors and prevents submission

---

### User Story 2 - Monitor Job Completion Status (Priority: P1)

A developer needs to watch as the worker processes their submitted generation job and see the results in real-time or near-real-time. They need visual feedback showing when a job transitions from pending → processing → completed, along with the generated image and any metadata.

**Why this priority**: Observing job completion is critical to E2E testing. Without this, developers can't verify that the entire pipeline works end-to-end. This directly tests the worker integration.

**Independent Test**: Can be fully tested by (1) submitting a test job, (2) polling/checking job status periodically, (3) confirming status transitions appear in the UI. Delivers value by enabling real-time pipeline monitoring.

**Acceptance Scenarios**:

1. **Given** a generation job is processing, **When** the developer refreshes the status, **Then** they see the current status ("pending", "processing", or "completed")
2. **Given** a generation job has completed successfully, **When** the developer views the job, **Then** they can see the output image URL and the generated image is displayed
3. **Given** a generation job fails, **When** the developer views the job, **Then** they can see the error message explaining why it failed
4. **Given** a completed job is displayed, **When** the developer views it, **Then** they can see processing_time_ms to understand performance

---

### User Story 3 - Job History and Exploration (Priority: P2)

A developer needs to see a list of previously submitted jobs, search through them, and drill into details without having to manually construct API calls. This helps with regression testing and understanding system behavior over time.

**Why this priority**: This enables efficient testing workflows - developers can quickly review past jobs and understand patterns. This makes testing more productive but isn't strictly necessary for basic E2E validation.

**Independent Test**: Can be fully tested by (1) submitting multiple jobs, (2) listing all jobs, (3) filtering/searching jobs, (4) viewing historical job details. Delivers value by enabling job history analysis.

**Acceptance Scenarios**:

1. **Given** multiple generation jobs exist, **When** the developer views the job list, **Then** they see all jobs paginated with basic info (ID, prompt preview, status, created date)
2. **Given** a job list is displayed, **When** the developer clicks a job, **Then** they navigate to detailed view with all job metadata
3. **Given** a detailed job view is displayed, **When** the developer wants to create a similar job, **Then** they can see a "retry" or "fork" option that pre-populates the form with the same parameters

---

### User Story 4 - Multi-Step Job Chains (Priority: P2)

A developer wants to test advanced workflows where one generation's output feeds into another as input (parent/child generation chains). They need to be able to fork a completed job or create a new generation based on a previous one's output.

**Why this priority**: This tests a more complex but important feature - generation chaining. It's secondary to basic job submission but important for comprehensive E2E testing of foreman's capabilities.

**Independent Test**: Can be fully tested by (1) completing a generation, (2) creating a child generation from it, (3) verifying parent/child relationship. Delivers value by enabling advanced workflow testing.

**Acceptance Scenarios**:

1. **Given** a completed generation exists, **When** the developer clicks "fork" or "chain", **Then** a new generation form opens with the parent generation's output pre-selected as input
2. **Given** a child generation is created from a parent, **When** the developer views the child, **Then** they can see the parent_id and trace back the generation history
3. **Given** a generation chain is created, **When** the developer views the parent, **Then** they can see that it has child generations linked to it

---

### Edge Cases

- What happens when a job is still processing and the developer refreshes the status?
- How does the UI handle network errors when fetching job status?
- What happens if the user tries to fork a failed or cancelled generation?
- How does the UI behave if a job takes an extremely long time to complete (timeout scenarios)?
- What happens if the worker crashes mid-processing? Can the UI display cancelled or failed states?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: UI MUST provide a user creation form that calls the `/v1/users/` endpoint and automatically extracts the returned user ID, storing it as the x-user-id for all subsequent API requests
- **FR-002**: UI MUST provide a settings panel where developers can manually enter and save their test x-user-id; this value MUST persist in localStorage for the session
- **FR-003**: UI MUST auto-discover the foreman API endpoint by first attempting to connect to `http://localhost:8000`; if that fails, MUST attempt dynamic discovery via `/.well-known/` or service registry
- **FR-004**: UI MUST allow developers to manually override the foreman API base URL in settings and persist it in localStorage
- **FR-005**: UI MUST display a project creation form allowing users to enter a project name and optional original image URL
- **FR-006**: UI MUST display a generation creation form with fields for prompt (required), style (optional dropdown), and parent_id (optional)
- **FR-007**: UI MUST submit generation requests to the foreman API and display the returned generation object with its ID
- **FR-008**: UI MUST support fetching and displaying the current status of a specific generation (pending, processing, completed, failed, cancelled)
- **FR-009**: UI MUST display generated output images when a generation reaches "completed" status with a valid output_image_url
- **FR-010**: UI MUST display error messages when a generation reaches "failed" status
- **FR-011**: UI MUST allow users to list projects they own
- **FR-012**: UI MUST allow users to list all generations or filter by project
- **FR-013**: UI MUST support cancelling a generation that is pending or processing
- **FR-014**: UI MUST support retrying a failed generation with the same original inputs
- **FR-015**: UI MUST support forking a completed generation to create a child generation using its output
- **FR-016**: UI MUST display job metadata including prompt, style, model_used, processing_time_ms, and timestamps
- **FR-017**: UI MUST handle API validation errors gracefully and display user-friendly error messages
- **FR-018**: UI MUST use the x-user-id (from user creation or manual entry) as the x-user-id header in all API requests
- **FR-019**: UI MUST warn users if x-user-id is not set before allowing API operations

### Key Entities

- **User**: Represents a test user with an ID, email, and full name. Needed to satisfy x-user-id header requirement.
- **Project**: Container for generations, has name, original_image_url, and owns multiple generations.
- **Generation**: Represents a single image generation job with status, prompt, inputs, outputs, and processing metadata.
- **Style**: Represents available design styles that can be applied to generations (fetched from API).
- **Image**: Represents stored images (inputs or outputs) with storage URLs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developers can create a generation job and see it appear in the system within under 2 seconds
- **SC-002**: Developers can monitor job status changes with latency under 1 second (from job completion to UI reflecting completion)
- **SC-003**: The UI supports testing all 5 primary generation endpoints (create, list, get, update status, cancel/retry/fork) without requiring API call construction
- **SC-004**: 95% of user interactions (form submissions, job creation, status polling) complete without JavaScript errors
- **SC-005**: New developers can create their first test generation job and see it progress through the pipeline within 5 minutes of opening the UI
- **SC-006**: The UI displays all critical generation metadata (status, prompt, output image, error message, processing time) correctly for any generated job state

## Clarifications

### Session 2026-05-13

- Q: How should users authenticate and provide x-user-id? → A: Option B - Manual entry in settings panel, persists in localStorage. **UPDATED**: Also support user creation through UI; creating a user automatically sets the x-user-id header.
- Q: How should the UI handle worker testing? → A: Option A - Real worker only. UI assumes workers are running and processing jobs normally.
- Q: How should the UI discover the foreman API endpoint? → A: Option D - Dynamic discovery with smart fallback. UI attempts to connect to `http://localhost:8000` by default; if that fails, attempts dynamic discovery via `/.well-known/` or other service registry mechanism.
- Q: How should the UI be deployed? → A: Option B - Standalone web app. UI is a separate directory (`foreman/ui/`) with static HTML/CSS/JavaScript files; developers serve it locally with `python -m http.server` or similar.

## Assumptions

- **Authentication**: Developers can create a test user through the UI (via the foreman user creation API) which returns a user ID; this ID is automatically set as the x-user-id header for all subsequent API requests. Alternatively, developers can manually enter an existing x-user-id in the settings panel; this value persists in localStorage and is used as the x-user-id header.
- **API Discovery**: The UI attempts to connect to `http://localhost:8000` as the default foreman API base URL. If this connection fails, the UI attempts dynamic discovery (e.g., via `/.well-known/` endpoint or service registry). Developers can manually override the API URL in settings if needed.
- **Project Initial State**: Developers can create at least one project before submitting generations; projects are not pre-seeded
- **Image Display**: Output images are accessible via public/signed URLs provided by the API; the UI doesn't need to handle image download/processing
- **Polling vs WebSocket**: Real-time status updates will use polling rather than WebSockets to keep the UI simple; polling interval can be configurable (default 2-5 seconds)
- **Scope**: The UI is a developer testing tool, not a production UI; visual design can be minimal/utilitarian. Deployed as static files (HTML/CSS/JavaScript) in `foreman/ui/` directory; developers serve locally with `python -m http.server 3000` or similar.
- **Data Retention**: Test data does not need to persist across server restarts; in-memory storage or session storage is acceptable
- **Worker**: Assumes real workers are running and processing jobs normally; workers transition jobs through normal lifecycle (pending → processing → completed/failed)
- **Styling Data**: The `/v1/styles/` endpoint will return available styles; the UI doesn't create or modify styles
- **Error Handling**: API errors will be returned with standard HTTP status codes and JSON error details; the UI should parse and display these cleanly
