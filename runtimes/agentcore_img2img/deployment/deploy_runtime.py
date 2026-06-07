from __future__ import annotations

import argparse
import io
import json
import random
import string
import subprocess
import sys
import tempfile
import time
import zipfile
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


def update_runtime(runtime_id: str, config_path: Path) -> dict[str, Any]:
    cfg = _load_config(config_path)
    region = cfg["region"]
    client = boto3.client("bedrock-agentcore-control", region_name=region)

    request: dict[str, Any] = {"agentRuntimeId": runtime_id}
    for field in (
        "agentRuntimeArtifact",
        "networkConfiguration",
        "roleArn",
        "lifecycleConfiguration",
    ):
        if field in cfg:
            request[field] = cfg[field]

    return client.update_agent_runtime(**request)


def get_runtime(runtime_id: str, region: str) -> dict[str, Any]:
    client = boto3.client("bedrock-agentcore-control", region_name=region)
    return client.get_agent_runtime(agentRuntimeId=runtime_id)


def list_runtimes(region: str) -> dict[str, Any]:
    client = boto3.client("bedrock-agentcore-control", region_name=region)
    return client.list_agent_runtimes()


def delete_runtime(runtime_id: str, region: str) -> dict[str, Any]:
    client = boto3.client("bedrock-agentcore-control", region_name=region)
    return client.delete_agent_runtime(agentRuntimeId=runtime_id)


def build_and_deploy(
    runtime_id: str,
    region: str,
    role_arn: str,
    model_id: str = "anthropic.claude-haiku-4-5-20251001-v1:0",
    output_base_url: str = "",
    allowed_input_domains: str = "",
) -> dict[str, Any]:
    """Package the local app/ folder into the deployed runtime ZIP and update the runtime.

    Strategy: download the current deployed ZIP as a dependency base (it contains the
    correct aarch64 Linux binaries for strands-agents), strip its main.py and any
    previously injected app files, then copy all local app/*.py flat to the ZIP root.
    app/main.py becomes main.py (the AgentCore entry point).
    """
    control = boto3.client("bedrock-agentcore-control", region_name=region)

    # --- 1. Find the current deployed artifact --------------------------------
    current = control.get_agent_runtime(agentRuntimeId=runtime_id)
    artifact = current["agentRuntimeArtifact"]["codeConfiguration"]["code"]["s3"]
    bucket = artifact["bucket"]
    current_key = artifact["prefix"]
    print(f"Base ZIP: s3://{bucket}/{current_key}")

    # --- 2. Download the base ZIP into memory ---------------------------------
    s3 = boto3.client("s3", region_name=region)
    base_buf = io.BytesIO()
    s3.download_fileobj(bucket, current_key, base_buf)
    base_buf.seek(0)
    print(f"Downloaded base ZIP ({base_buf.getbuffer().nbytes // 1024} KB)")

    # --- 3. Build the new ZIP -------------------------------------------------
    new_buf = io.BytesIO()
    app_dir = Path(__file__).parent.parent / "app"
    app_py_names = {f.name for f in app_dir.glob("*.py") if f.name != "__init__.py"}

    # Install extra packages for linux/aarch64 (the AgentCore runtime architecture)
    # into a temp dir so we can bundle them into the ZIP.
    _EXTRA_PACKAGES = ["Pillow"]

    with tempfile.TemporaryDirectory() as tmp_pkg_dir:
        print(f"Installing extra packages for linux/aarch64: {_EXTRA_PACKAGES}")
        subprocess.check_call(
            [
                sys.executable, "-m", "pip", "install",
                "--quiet",
                "--target", tmp_pkg_dir,
                "--platform", "manylinux2014_aarch64",
                "--implementation", "cp",
                "--python-version", "3.13",
                "--only-binary=:all:",
            ] + _EXTRA_PACKAGES,
        )

        with zipfile.ZipFile(base_buf, "r") as base_zip, \
             zipfile.ZipFile(new_buf, "w", zipfile.ZIP_DEFLATED) as new_zip:

            # Collect names already present in the base ZIP so we don't double-bundle
            existing_names = set(base_zip.namelist())

            # Copy every entry from the base ZIP except:
            #   - main.py  (the stub / previous entry point we replace)
            #   - any app/*.py previously injected flat at root
            skipped = {"main.py"} | app_py_names
            for item in base_zip.infolist():
                if item.filename not in skipped:
                    new_zip.writestr(item, base_zip.read(item.filename))

            # Bundle extra packages (only files not already in base ZIP)
            tmp_pkg_path = Path(tmp_pkg_dir)
            added_pkg_files = 0
            for pkg_file in sorted(tmp_pkg_path.rglob("*")):
                if pkg_file.is_file():
                    arcname = pkg_file.relative_to(tmp_pkg_path).as_posix()
                    if arcname not in existing_names:
                        new_zip.write(pkg_file, arcname)
                        added_pkg_files += 1
            print(f"  + {added_pkg_files} extra package files bundled")

            # Copy app/*.py flat to ZIP root (excluding __init__.py — not needed at root).
            # Flat layout means main.py can do `from graph import run_graph` etc.
            for py_file in sorted(app_dir.glob("*.py")):
                if py_file.name == "__init__.py":
                    continue
                new_zip.write(py_file, py_file.name)
                print(f"  + {py_file.name}")

    new_buf.seek(0)
    print(f"New ZIP built ({new_buf.getbuffer().nbytes // 1024} KB)")

    # --- 4. Upload new ZIP to S3 ----------------------------------------------
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    new_key = f"{int(time.time() * 1000)}-{suffix}-foreman_runtime.zip"
    s3.upload_fileobj(new_buf, bucket, new_key)
    print(f"Uploaded: s3://{bucket}/{new_key}")

    # --- 5. Update the runtime ------------------------------------------------
    env_vars: dict[str, str] = {"RUNTIME_STRANDS_MODEL_ID": model_id}
    if output_base_url:
        env_vars["RUNTIME_OUTPUT_BASE_URL"] = output_base_url
    if allowed_input_domains:
        env_vars["RUNTIME_ALLOWED_INPUT_DOMAINS"] = allowed_input_domains

    result = control.update_agent_runtime(
        agentRuntimeId=runtime_id,
        roleArn=role_arn,
        agentRuntimeArtifact={
            "codeConfiguration": {
                "code": {"s3": {"bucket": bucket, "prefix": new_key}},
                "runtime": "PYTHON_3_13",
                "entryPoint": ["main.py"],
            }
        },
        networkConfiguration={"networkMode": "PUBLIC"},
        environmentVariables=env_vars,
    )
    print("Runtime updated.")
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy and inspect AgentCore runtimes")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create runtime from json config")
    create.add_argument("--config", required=True, type=Path)

    update = sub.add_parser("update", help="Update runtime from json config")
    update.add_argument("--runtime-id", required=True)
    update.add_argument("--config", required=True, type=Path)

    get = sub.add_parser("get", help="Get runtime by runtime id")
    get.add_argument("--runtime-id", required=True)
    get.add_argument("--region", required=True)

    list_cmd = sub.add_parser("list", help="List runtimes")
    list_cmd.add_argument("--region", required=True)

    delete = sub.add_parser("delete", help="Delete runtime by runtime id")
    delete.add_argument("--runtime-id", required=True)
    delete.add_argument("--region", required=True)

    build_deploy = sub.add_parser("build-deploy", help="Package and deploy local app/ code")
    build_deploy.add_argument("--runtime-id", required=True)
    build_deploy.add_argument("--region", required=True)
    build_deploy.add_argument("--role-arn", required=True)
    build_deploy.add_argument(
        "--model-id",
        default="anthropic.claude-haiku-4-5-20251001-v1:0",
        help="Bedrock model ID for the Strands agent (RUNTIME_STRANDS_MODEL_ID)",
    )
    build_deploy.add_argument(
        "--output-base-url",
        default="",
        help="Base URL for generated image output (RUNTIME_OUTPUT_BASE_URL)",
    )
    build_deploy.add_argument(
        "--allowed-input-domains",
        default="",
        help="Comma-separated input image domain allowlist (RUNTIME_ALLOWED_INPUT_DOMAINS)",
    )

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.command == "create":
        result = create_runtime(args.config)
    elif args.command == "update":
        result = update_runtime(args.runtime_id, args.config)
    elif args.command == "get":
        result = get_runtime(args.runtime_id, args.region)
    elif args.command == "delete":
        result = delete_runtime(args.runtime_id, args.region)
    elif args.command == "build-deploy":
        result = build_and_deploy(
            runtime_id=args.runtime_id,
            region=args.region,
            role_arn=args.role_arn,
            model_id=args.model_id,
            output_base_url=args.output_base_url,
            allowed_input_domains=args.allowed_input_domains,
        )
    else:
        result = list_runtimes(args.region)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
