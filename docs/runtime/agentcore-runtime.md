# AgentCore Runtime Operations Guide

## Overview
This module hosts the img2img runtime as an independent deployable for AgentCore.
It must remain compatible with existing worker request/response contract while keeping worker/Foreman unchanged.

## Deployment Requirements
- ARM64 container image
- Runtime listens on `0.0.0.0:8080`
- `GET /ping` and `POST /invocations` implemented
- Runtime role configured with least-privilege permissions

## Runtime Environment Variables
- `RUNTIME_OUTPUT_BASE_URL` (required): remote base URL used to build canonical `output_image_url`
- `RUNTIME_ALLOWED_INPUT_DOMAINS` (optional): comma-separated host allowlist for `input_image_url`
- `RUNTIME_MODEL_USED` (optional): metadata model label returned to caller

## Invocation Contract Notes
Required payload fields:
- `prompt`
- `generation_id`
- `input_image_url`

Optional payload fields:
- `style_id`
- `runtime_session_id`

Required headers:
- `x-user-id`

Success response:
- `output_image_url` (required)
- `generated_image_description` (optional)
- `model_used` (optional)

Prohibited response fields:
- `binary_image`
- `image_bytes`
- `raw_image`

## Security Validation Workflow
1. Call `/invocations` with allowed input domain and `x-user-id`; expect success.
2. Call `/invocations` without `x-user-id`; expect 403 deny.
3. Call `/invocations` with disallowed input domain; expect 403 deny.
4. Validate deny/success audit events include `generation_id`, `runtime_session_id`, and `user_id`.

## Outage, Rollback, and Redeploy
1. Detect outage by failed `/ping` or elevated `invocation_failed` events.
2. Roll back runtime alias/version to last healthy deployment.
3. Redeploy fixed image and rerun contract validation tests.
4. Confirm `/ping` healthy and sample `/invocations` returns metadata-only output.
