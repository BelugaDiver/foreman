# AgentCore IAM Boundary

This document defines least-privilege boundaries for Foreman worker and AgentCore runtime roles.

## Worker Role Permissions

Allowed:
- sqs:ReceiveMessage
- sqs:DeleteMessage
- sqs:ChangeMessageVisibility
- sqs:SendMessage (dead-letter queue only)
- bedrock-agentcore:InvokeAgentRuntime

Disallowed:
- s3:PutObject
- s3:DeleteObject

## AgentCore Runtime Role Permissions

Allowed:
- s3:PutObject (artifact output path only)
- s3:GetObject (if runtime needs source assets)

Disallowed:
- SQS consume/delete on worker queue

## Example Worker Policy Snippet

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "QueueReadDelete",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility"
      ],
      "Resource": "arn:aws:sqs:us-east-1:123456789012:foreman-generations"
    },
    {
      "Sid": "DeadLetterSend",
      "Effect": "Allow",
      "Action": ["sqs:SendMessage"],
      "Resource": "arn:aws:sqs:us-east-1:123456789012:foreman-generations-dlq"
    },
    {
      "Sid": "AgentCoreInvoke",
      "Effect": "Allow",
      "Action": ["bedrock-agentcore:InvokeAgentRuntime"],
      "Resource": "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/my-runtime"
    }
  ]
}
```
