# AgentCore Img2Img Runtime Host

Standalone runtime host module for Amazon Bedrock AgentCore deployment.

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
- `x-user-id` (required)

## Local Run
```bash
uvicorn runtimes.agentcore_img2img.app.main:app --host 0.0.0.0 --port 8080
```

## Local Test
```bash
python -m pytest runtimes/agentcore_img2img/tests -q
```
