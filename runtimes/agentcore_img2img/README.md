# AgentCore Img2Img Runtime Host

Standalone runtime host module for Amazon Bedrock AgentCore deployment.

## Dependencies
- Python package requirements are managed via root `pyproject.toml`.
- Strands runtime dependency: `strands-agents[bedrock]`.

## Runtime Contract
- Host: `0.0.0.0`
- Port: `8080`
- Health endpoint: `GET /ping`
- Invocation endpoint: `POST /invocations`

## Invocation Payload
```json
{
  "prompt": "A cinematic portrait",
  "generation_id": "f0cf0f84-c711-47a8-a884-62113795e003",
  "input_image_url": "https://cdn.example.com/input.png",
  "style_id": "noir",
  "runtime_session_id": "proj-f0cf0f84"
}
```

## Invocation Headers
- None required. `boto3` `invoke_agent_runtime` does not forward custom headers to the container; the runtime is user-agnostic.

## Local Run
```bash
uvicorn runtimes.agentcore_img2img.app.main:app --host 0.0.0.0 --port 8080
```

## Local Test
```bash
python -m pytest runtimes/agentcore_img2img/tests -q
```

## Control Plane Lifecycle
```bash
python -m runtimes.agentcore_img2img.deployment.deploy_runtime create --config runtimes/agentcore_img2img/deployment/runtime-config.example.json
python -m runtimes.agentcore_img2img.deployment.deploy_runtime list --region us-west-2
python -m runtimes.agentcore_img2img.deployment.deploy_runtime get --runtime-id <runtime-id> --region us-west-2
python -m runtimes.agentcore_img2img.deployment.deploy_runtime update --runtime-id <runtime-id> --config runtimes/agentcore_img2img/deployment/runtime-config.example.json
python -m runtimes.agentcore_img2img.deployment.deploy_runtime delete --runtime-id <runtime-id> --region us-west-2
```
