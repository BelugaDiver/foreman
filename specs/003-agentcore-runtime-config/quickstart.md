# Quickstart: AgentCore Runtime Host Module

## 1. Confirm environment and scope
1. Ensure you are on branch 003-agentcore-runtime-config.
2. Confirm this feature scope is runtime-host only.
3. Confirm Foreman API and worker code remain unchanged.

## 2. Configure runtime host inputs (dev-only rollout)
1. Set `RUNTIME_OUTPUT_BASE_URL` to a worker-accessible remote URL prefix.
2. Optionally set `RUNTIME_ALLOWED_INPUT_DOMAINS` as a comma-separated allowlist.
3. Optionally set `RUNTIME_MODEL_USED` for response metadata.
4. Use development environment only for initial rollout.

## 3. Run runtime host locally
1. Start runtime host:
   - `uvicorn runtimes.agentcore_img2img.app.main:app --host 0.0.0.0 --port 8080`
2. Validate health endpoint:
   - `curl http://localhost:8080/ping`

## 4. Validate runtime request/response contract
1. Send invocation request:
   - include `prompt`, `generation_id`, `input_image_url`
   - optionally include `style_id`, `runtime_session_id`
   - include header `x-user-id`
2. Verify success response contains:
   - `output_image_url` (required)
   - `generated_image_description` (optional)
   - `model_used` (optional)
3. Verify response does not include `binary_image`, `image_bytes`, or `raw_image`.

## 5. Validate security boundaries
1. Call `/invocations` without `x-user-id` and verify deny (403).
2. Configure `RUNTIME_ALLOWED_INPUT_DOMAINS` and call with disallowed host; verify deny (403).
3. Verify denial events are emitted with generation/session/user context.

## 6. Incident-response quick checklist
1. Confirm `/ping` status and dependency status.
2. Check runtime logs for `invocation_failed` and `invocation_denied` events.
3. Roll back runtime alias/version to last known good image if needed.
4. Redeploy fixed image and rerun contract tests before restoring traffic.

## 7. Final verification command matrix
1. Contract/unit checks:
   - `python -m pytest runtimes/agentcore_img2img/tests/test_contracts.py -q`
   - `python -m pytest runtimes/agentcore_img2img/tests/test_authz.py -q`
2. Integration checks:
   - `python -m pytest runtimes/agentcore_img2img/tests/integration/test_runtime_contract.py -q`
   - `python -m pytest runtimes/agentcore_img2img/tests/integration/test_runtime_iam_boundary.py -q`
   - `python -m pytest runtimes/agentcore_img2img/tests/integration/test_runtime_recovery.py -q`
3. Health checks:
   - `python -m pytest runtimes/agentcore_img2img/tests/test_health.py -q`
