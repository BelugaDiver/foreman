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
    prompt_rewrite_model_id: str = "",
    sd_model_id: str = "",
    controlnet_mode: str = "",
    verification_alignment_threshold: str = "",
    verification_max_iterations: str = "",
    verification_time_budget_seconds: str = "",
    verification_iter_estimate_seconds: str = "",
    max_output_image_bytes: str = "",
    sd_prompt_max_tokens: str = "",
    correction_context_max_tokens: str = "",
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
    stages_dir = app_dir / "stages"
    stages_py_names = {f"stages/{f.name}" for f in stages_dir.glob("*.py")} if stages_dir.is_dir() else set()

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
            #   - any stages/*.py previously injected (will be replaced from local)
            skipped = {"main.py"} | app_py_names | stages_py_names
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

            # Copy app/stages/ subdirectory, preserving the package structure.
            stages_dir = app_dir / "stages"
            if stages_dir.is_dir():
                for py_file in sorted(stages_dir.glob("*.py")):
                    arcname = f"stages/{py_file.name}"
                    new_zip.write(py_file, arcname)
                    print(f"  + {arcname}")

    new_buf.seek(0)
    print(f"New ZIP built ({new_buf.getbuffer().nbytes // 1024} KB)")

    # --- 4. Upload new ZIP to S3 ----------------------------------------------
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    new_key = f"{int(time.time() * 1000)}-{suffix}-foreman_runtime.zip"
    s3.upload_fileobj(new_buf, bucket, new_key)
    print(f"Uploaded: s3://{bucket}/{new_key}")

    # --- 5. Update the runtime ------------------------------------------------
    _pipeline_vars = {
        "PROMPT_REWRITE_MODEL_ID": prompt_rewrite_model_id,
        "SD_MODEL_ID": sd_model_id,
        "CONTROLNET_MODE": controlnet_mode,
        "VERIFICATION_ALIGNMENT_THRESHOLD": verification_alignment_threshold,
        "VERIFICATION_MAX_ITERATIONS": verification_max_iterations,
        "VERIFICATION_TIME_BUDGET_SECONDS": verification_time_budget_seconds,
        "VERIFICATION_ITER_ESTIMATE_SECONDS": verification_iter_estimate_seconds,
        "MAX_OUTPUT_IMAGE_BYTES": max_output_image_bytes,
        "SD_PROMPT_MAX_TOKENS": sd_prompt_max_tokens,
        "CORRECTION_CONTEXT_MAX_TOKENS": correction_context_max_tokens,
        "RUNTIME_ALLOWED_INPUT_DOMAINS": allowed_input_domains,
    }
    env_vars: dict[str, str] = {k: v for k, v in _pipeline_vars.items() if v}

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
        "--prompt-rewrite-model-id", default="",
        help="Bedrock model ID for Stage 1 + Stage 3 (PROMPT_REWRITE_MODEL_ID)",
    )
    build_deploy.add_argument(
        "--sd-model-id", default="",
        help="Bedrock model ID for Stable Diffusion ControlNet (SD_MODEL_ID)",
    )
    build_deploy.add_argument(
        "--controlnet-mode", default="", choices=["", "depth", "edge"],
        help="ControlNet conditioning mode: depth or edge (CONTROLNET_MODE)",
    )
    build_deploy.add_argument(
        "--verification-alignment-threshold", default="",
        help="Composite score 0-1 to exit loop early (VERIFICATION_ALIGNMENT_THRESHOLD)",
    )
    build_deploy.add_argument(
        "--verification-max-iterations", default="",
        help="Hard cap on verification loop iterations (VERIFICATION_MAX_ITERATIONS)",
    )
    build_deploy.add_argument(
        "--verification-time-budget-seconds", default="",
        help="Wall-clock budget in seconds for the verification loop (VERIFICATION_TIME_BUDGET_SECONDS)",
    )
    build_deploy.add_argument(
        "--verification-iter-estimate-seconds", default="",
        help="Estimated seconds per SD + verify round-trip (VERIFICATION_ITER_ESTIMATE_SECONDS)",
    )
    build_deploy.add_argument(
        "--max-output-image-bytes", default="",
        help="Ceiling for output image size in bytes (MAX_OUTPUT_IMAGE_BYTES)",
    )
    build_deploy.add_argument(
        "--sd-prompt-max-tokens", default="",
        help="Character limit for enriched prompt passed to SD (SD_PROMPT_MAX_TOKENS)",
    )
    build_deploy.add_argument(
        "--correction-context-max-tokens", default="",
        help="Character limit for correction context fed back to Stage 1 (CORRECTION_CONTEXT_MAX_TOKENS)",
    )
    build_deploy.add_argument(
        "--allowed-input-domains", default="",
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
            prompt_rewrite_model_id=args.prompt_rewrite_model_id,
            sd_model_id=args.sd_model_id,
            controlnet_mode=args.controlnet_mode,
            verification_alignment_threshold=args.verification_alignment_threshold,
            verification_max_iterations=args.verification_max_iterations,
            verification_time_budget_seconds=args.verification_time_budget_seconds,
            verification_iter_estimate_seconds=args.verification_iter_estimate_seconds,
            max_output_image_bytes=args.max_output_image_bytes,
            sd_prompt_max_tokens=args.sd_prompt_max_tokens,
            correction_context_max_tokens=args.correction_context_max_tokens,
            allowed_input_domains=args.allowed_input_domains,
        )
    else:
        result = list_runtimes(args.region)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
