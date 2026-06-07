# Implementation Plan: AgentCore Runtime Configuration

**Branch**: `003-agentcore-runtime-config` | **Date**: 2026-05-30 | **Spec**: /specs/003-agentcore-runtime-config/spec.md
**Input**: Feature specification from `/specs/003-agentcore-runtime-config/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Build and deploy a standalone AgentCore runtime host module that is independently versioned and deployable, while preserving strict compatibility with the existing worker request/response contract. The implementation focuses on runtime hosting contract compliance (ARM64, 0.0.0.0:8080, /ping, /invocations), metadata-only outputs, tenant-aware access boundaries, runtime telemetry, and dev-only rollout.

## Simplification Direction (2026-06-01)

Reduce internal runtime complexity by using a functional graph core (`run_graph`) instead of adapter/result classes, while preserving all external contracts and telemetry semantics. Keep code paths explicit and linear: validate request -> enforce policy -> run graph function -> map metadata response.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: Python 3.11+, FastAPI or equivalent HTTP runtime host, selected agent framework (Strands-first), boto3 (bedrock-agentcore-control and bedrock-agentcore), OpenTelemetry, pytest  
**Storage**: External image/object storage URLs only; no local binary response payload storage in runtime response path  
**Testing**: pytest (unit and integration for runtime host module only)  
**Target Platform**: ARM64 Linux container deployed to Amazon Bedrock AgentCore Runtime
**Project Type**: Standalone runtime service module  
**Performance Goals**: Meet SC-002 and SC-003 from spec (>=95% invocation acceptance within 60s in normal dev ops; detect incidents within 5 minutes)  
**Constraints**: Foreman and worker remain unchanged; metadata-only outputs; runtime-compatible contract with current worker expectations; dev-only first rollout  
**Scale/Scope**: One feature slice scoped to the new runtime host deployable and its deployment operations

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*
*Reference: `.specify/memory/constitution.md`*

- [x] **I. Layered Architecture** — change is isolated to a standalone runtime module; existing foreman and worker layers remain untouched.
- [x] **II. Raw SQL** — no ORM or repository layer replacement introduced by this feature.
- [x] **III. Async-First** — runtime host request handling and model integration remain async-first.
- [x] **IV. Event-Driven** — runtime module is invoked by existing event-driven worker flow without altering upstream pipeline.
- [x] **V. Protocols** — runtime module enforces stable invocation/response contract, independent of internal framework details.
- [x] **VI. Test Layers** — plan includes runtime-host unit and integration validation for contract, security, and operations.
- [x] **VII. Observability** — runtime session, generation correlation, and failure telemetry are mandatory in the runtime host.
- [x] **VIII. Security** — least-privilege runtime IAM and tenant context checks are first-class requirements.

## Project Structure

### Documentation (this feature)

```text
specs/003-agentcore-runtime-config/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
```text
runtimes/
└── agentcore_img2img/
    ├── app/
    ├── deployment/
    ├── tests/
    └── Dockerfile

docs/runtime/
```

**Structure Decision**: Introduce a dedicated runtime-host module under runtimes/agentcore_img2img. Keep existing foreman and worker code unchanged, and enforce compatibility through runtime contract tests and deployment documentation.

## Post-Design Constitution Check

- [x] **I. Layered Architecture** — design artifacts preserve foreman/worker boundaries by making runtime host a separate module.
- [x] **II. Raw SQL** — no ORM introduction; repository contract remains unchanged.
- [x] **III. Async-First** — runtime host contract handlers and framework calls remain async-first.
- [x] **IV. Event-Driven** — existing queue-first processing remains unchanged; runtime host is a downstream target.
- [x] **V. Protocols** — runtime invocation and response protocol remains stable regardless of framework internals.
- [x] **VI. Test Layers** — runtime host tests cover contract, deployment checks, and operational behavior.
- [x] **VII. Observability** — runtime correlation and failure telemetry are explicit runtime requirements.
- [x] **VIII. Security** — runtime IAM boundaries and tenant-context gating are explicit runtime requirements.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations identified.

## Implementation Status

- Status: Completed for runtime-host scope.
- Status: Completed for runtime-host scope with simplification pass applied.
- Completion Date: 2026-05-30.
- Delivered artifacts:
    - Standalone runtime module under `runtimes/agentcore_img2img/`.
    - Runtime host endpoints `/ping` and `/invocations` with worker-compatible contracts.
    - Runtime policy/authz/telemetry/health components and deployment utilities.
    - Runtime-focused docs and verification matrix under `docs/runtime/` and feature quickstart.
    - Runtime-focused tests for contract, IAM boundaries, health, recovery, and audit completeness.
- Validation:
    - `python -m pytest runtimes/agentcore_img2img/tests -q` passed (16 tests).
