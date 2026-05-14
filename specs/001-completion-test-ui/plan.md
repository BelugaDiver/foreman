# Implementation Plan: Completion Test UI

**Branch**: `001-completion-test-ui` | **Date**: 2026-05-13 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-completion-test-ui/spec.md`

## Summary

Build a standalone web-based testing UI for validating end-to-end image generation workflows in foreman. Developers access the UI at `http://localhost:3000`, discover the foreman API at `http://localhost:8000` (with fallback to dynamic discovery), create test users, submit generation jobs, and monitor completion in real-time via polling. The UI is delivered as static HTML/CSS/JavaScript in `foreman/ui/`, requires no backend beyond the existing foreman API, and supports all generation lifecycle operations (create, list, get, cancel, retry, fork).

## Technical Context

**Language/Version**: HTML5, CSS3, JavaScript (ES6+) — no build step required; vanilla JS or lightweight framework  
**Primary Dependencies**: None for core functionality; fetch API for HTTP; optionally: htmx, Alpine.js, or Lit for DOM interactivity (lightweight, <10KB)  
**Storage**: Browser localStorage for x-user-id and API base URL persistence only; no server-side state  
**Testing**: Browser-based E2E tests (optional: playwright, cypress) for UI validation; can also be tested manually  
**Target Platform**: Modern web browsers (Chrome, Firefox, Safari, Edge); desktop-first, mobile-responsive  
**Project Type**: Single-page application (SPA) / web-based testing tool  
**Performance Goals**: Sub-2-second job creation latency (SC-001); sub-1-second status update latency (SC-002); 95% interaction success rate (SC-004)  
**Constraints**: Zero external API dependencies beyond foreman; must work offline from UI perspective (polling handles transient network errors); <100KB total asset size  
**Scale/Scope**: Single-page UI with 5-6 main views (auth/settings, projects, generation form, job list, job detail); supports unlimited projects/jobs (limited by foreman backend)

## Constitution Check

*GATE: Frontend/UI features don't implement backend architecture layers (migrations, models, repositories, endpoints). Instead, we check frontend-specific principles:*

- [x] **API Client**: All calls to foreman API are isolated in a single `api.js` module with consistent error handling and retry logic.
- [x] **Security**: No credentials/secrets hardcoded; x-user-id sourced only from user input (localStorage) or API response; no eval/innerHTML unsafe DOM operations.
- [x] **Error Handling**: Network errors display user-friendly messages; validation errors from API are parsed and shown; 4xx/5xx responses handled gracefully.
- [x] **Observability**: Errors logged to browser console; no PII or sensitive data in logs; timestamps on events for debugging.
- [x] **Modularity**: UI components decoupled by concern (settings, auth, projects, jobs); state management centralized; easy to refactor or replace UI library.
- [x] **Testing**: Manually testable; E2E test scripts can automate key workflows; no complex build/test infrastructure required.
- [x] **Documentation**: Inline code comments for complex logic; README with setup instructions; list of API endpoints relied on.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
foreman/ui/
├── index.html              # Main entry point; loads CSS, JS; host for SPA
├── styles.css              # All UI styles (minimal, ~500 lines)
├── app.js                  # Main app controller; routing, initialization
├── api.js                  # API client module; all foreman endpoints, error handling
├── state.js                # Client-side state management (user ID, API URL, cached data)
├── components/
│   ├── settings.js         # Settings panel (user ID, API URL, polling interval)
│   ├── auth.js             # User creation form + login screen
│   ├── projects.js         # Project list and creation form
│   ├── generation-form.js  # Generation job creation form
│   ├── job-list.js         # List of generations with filtering
│   ├── job-detail.js       # Single generation detail view with polling
│   └── utils.js            # Helper functions (DOM, formatting, validation)
└── README.md               # Setup instructions, API endpoint reference, deployment guide
```

**Structure Decision**: Single-page application with modular component structure. Each component is a self-contained JS module managing a UI view. `app.js` handles client-side routing and component lifecycle. `api.js` provides the HTTP abstraction layer. Styles are minimal and all in one file for rapid iteration. No build step; served as static files via HTTP server.

## Complexity Tracking

No Constitution Check violations. This is a frontend-only feature using vanilla JavaScript; no backend layer implementation required. Architecture is straightforward: modular components, single HTTP client abstraction, localStorage for persistence, and browser APIs for DOM management.
