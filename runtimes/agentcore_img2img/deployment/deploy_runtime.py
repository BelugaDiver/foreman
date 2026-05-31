from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import boto3


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def create_runtime(config_path: Path) -> dict[str, Any]:
    cfg = _load_config(config_path)
    region = cfg["region"]
    client = boto3.client("bedrock-agentcore-control", region_name=region)
    return client.create_agent_runtime(
        agentRuntimeName=cfg["agentRuntimeName"],
        agentRuntimeArtifact=cfg["agentRuntimeArtifact"],
        networkConfiguration=cfg["networkConfiguration"],
        roleArn=cfg["roleArn"],
        lifecycleConfiguration=cfg.get("lifecycleConfiguration", {}),
    )


def get_runtime(runtime_id: str, region: str) -> dict[str, Any]:
    client = boto3.client("bedrock-agentcore-control", region_name=region)
    return client.get_agent_runtime(agentRuntimeId=runtime_id)


def list_runtimes(region: str) -> dict[str, Any]:
    client = boto3.client("bedrock-agentcore-control", region_name=region)
    return client.list_agent_runtimes()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy and inspect AgentCore runtimes")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create runtime from json config")
    create.add_argument("--config", required=True, type=Path)

    get = sub.add_parser("get", help="Get runtime by runtime id")
    get.add_argument("--runtime-id", required=True)
    get.add_argument("--region", required=True)

    list_cmd = sub.add_parser("list", help="List runtimes")
    list_cmd.add_argument("--region", required=True)

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.command == "create":
        result = create_runtime(args.config)
    elif args.command == "get":
        result = get_runtime(args.runtime_id, args.region)
    else:
        result = list_runtimes(args.region)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
