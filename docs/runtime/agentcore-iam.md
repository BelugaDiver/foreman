# AgentCore Runtime IAM Boundaries

## Runtime Invocation Caller Policy
Grant to caller (worker or test principal invoking runtime):
- `bedrock-agentcore:InvokeAgentRuntime` on target runtime ARN

## Runtime Execution Role Policy
Grant only what runtime host needs:
- Model invocation permissions limited to selected model/runtime dependencies
- Read access only for approved input artifact locations
- Write access only for approved output artifact locations
- Logging/telemetry permissions required by runtime observability stack

Do not grant:
- SQS consume/delete permissions for worker queue
- Broad wildcard actions on all resources

## Tenant Context Enforcement
Runtime requires caller-provided user context (`x-user-id`) at invocation boundary.
Requests without required tenant context are denied before graph execution.

## Allow/Deny Matrix
- Allow: valid `x-user-id` + allowed `input_image_url` host + contract-valid payload
- Deny: missing `x-user-id`
- Deny: `input_image_url` host not in allowlist (when allowlist configured)
- Deny: invalid invocation payload
