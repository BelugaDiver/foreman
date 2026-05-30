"""Integration-style policy boundary checks for AgentCore worker/runtime IAM split."""

from __future__ import annotations

import json
from pathlib import Path


def _extract_json_policy(markdown_text: str) -> dict:
    start = markdown_text.find("```json")
    end = markdown_text.find("```", start + 7)
    assert start != -1 and end != -1, "Expected JSON policy block in IAM documentation"
    json_text = markdown_text[start + 7 : end].strip()
    return json.loads(json_text)


def test_worker_policy_allows_agentcore_invoke_and_queue_operations_only():
    """Worker policy should include queue access + AgentCore invoke and no direct S3 write."""
    path = Path("docs/worker/agentcore-iam.md")
    policy = _extract_json_policy(path.read_text())

    actions = []
    for statement in policy.get("Statement", []):
        stmt_actions = statement.get("Action", [])
        if isinstance(stmt_actions, str):
            actions.append(stmt_actions)
        else:
            actions.extend(stmt_actions)

    assert "bedrock-agentcore:InvokeAgentRuntime" in actions
    assert "sqs:ReceiveMessage" in actions
    assert "sqs:DeleteMessage" in actions
    assert "sqs:SendMessage" in actions
    assert "s3:PutObject" not in actions
