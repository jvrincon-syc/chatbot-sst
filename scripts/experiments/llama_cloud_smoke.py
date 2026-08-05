from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from ingestion.config.llama_settings import load_llama_settings
from core.logging.logger import configure_structured_logging  # noqa: E402
from ingestion.infrastructure.llama_cloud.classify_config import LlamaClassifyConfig
from ingestion.infrastructure.llama_cloud.classify_rules import classification_labels
from ingestion.infrastructure.llama_cloud.extract_config import LlamaExtractConfig
from ingestion.infrastructure.llama_cloud.parse_config import LlamaParseConfig


def main() -> int:
    configure_structured_logging(stream=sys.stderr, include_file_handler=False)
    logger = logging.getLogger(__name__)
    parser = argparse.ArgumentParser(description="Guarded Llama Cloud smoke test.")
    parser.add_argument("--document-id", default="synthetic-llama-smoke")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/llama_first/smoke-results.json"))
    parser.add_argument("--secrets-env", type=Path, default=Path("secrets.env"))
    args = parser.parse_args()

    _load_secrets_env(args.secrets_env)
    source = args.source or _ensure_synthetic_source()
    live_enabled = _env_bool("LLAMA_CLOUD_LIVE")
    if args.source is not None and not live_enabled:
        result = {
            "schema_version": "1.0",
            "run_id": "blocked-source-upload-requires-live-authorization",
            "status": "blocked",
            "document_id": args.document_id,
            "capabilities": [],
            "provider_job_ids": [],
            "credits": 0,
            "elapsed_seconds": 0,
            "warnings": [
                "Set LLAMA_CLOUD_LIVE=true before uploading a provided source file."
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        logger.warning(
            "llama_smoke_blocked",
            extra={
                "stage": "evaluation",
                "event": "llama_smoke_blocked",
                "status": "blocked",
                "document_id": args.document_id,
                "output": str(args.output),
            },
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2

    try:
        settings = load_llama_settings()
    except ValueError as exc:
        result = _blocked_result(args.document_id, f"settings_error:{exc}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        logger.warning(
            "llama_smoke_blocked",
            extra={
                "stage": "evaluation",
                "event": "llama_smoke_blocked",
                "status": "blocked",
                "document_id": args.document_id,
                "output": str(args.output),
            },
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2

    if not settings.cloud_enabled:
        result = _blocked_result(args.document_id, "LLAMA_CLOUD_ENABLED is false")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        logger.warning(
            "llama_smoke_blocked",
            extra={
                "stage": "evaluation",
                "event": "llama_smoke_blocked",
                "status": "blocked",
                "document_id": args.document_id,
                "output": str(args.output),
            },
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2

    from llama_cloud import AsyncLlamaCloud

    client = AsyncLlamaCloud(api_key=settings.api_key.get_secret_value())
    result = asyncio.run(
        run_live_smoke(
            client=client,
            source=source,
            output=args.output,
            document_id=args.document_id,
        )
    )
    logger.info(
        "llama_smoke_completed",
        extra={
            "stage": "evaluation",
            "event": "llama_smoke_completed",
            "status": result["status"],
            "document_id": args.document_id,
            "output": str(args.output),
        },
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "completed" else 1


async def run_live_smoke(
    *,
    client: object,
    source: Path,
    output: Path,
    document_id: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    settings = load_llama_settings()
    parse_config = LlamaParseConfig.from_settings(settings)
    classify_config = LlamaClassifyConfig(
        mode=settings.classify_mode,
        language=settings.parse_ocr_languages[0] if settings.parse_ocr_languages else "es",
        max_pages=settings.classify_max_pages,
    )
    extract_config = LlamaExtractConfig(
        schema_name="document_control_smoke",
        critical_fields=("document_title", "document_code"),
        data_schema=_smoke_extract_schema(),
        tier=settings.extract_tier,
        parse_tier=settings.extract_parse_tier,
        version=settings.parse_version,
        max_pages=settings.extract_max_pages,
    )

    parse_response = await client.parsing.parse(
        upload_file=source,
        **parse_config.to_parse_kwargs(),
    )
    parse_payload = _payload(parse_response)
    parse_job_id = _job_id(parse_payload)
    await client.parsing.get(parse_job_id, expand=["metadata", "job_metadata"])

    labels = tuple(classification_labels().keys())
    classify_response = await client.classify.run(
        file_input=parse_job_id,
        configuration=classify_config.to_run_configuration(labels=labels),
    )
    extract_response = await client.extract.run(
        file_input=parse_job_id,
        configuration=extract_config.to_run_configuration(),
    )

    classify_payload = _payload(classify_response)
    extract_payload = _payload(extract_response)
    elapsed = round(time.perf_counter() - started, 3)
    result = {
        "schema_version": "1.0",
        "run_id": f"llama-smoke-{int(time.time())}",
        "status": "completed",
        "document_id": document_id,
        "source_kind": "synthetic" if source.name == "synthetic_llama_smoke.md" else "provided",
        "capabilities": ["parse", "classify", "extract"],
        "provider_job_ids": [
            parse_job_id,
            str(classify_payload.get("id") or classify_payload.get("job_id") or "unknown"),
            str(extract_payload.get("id") or extract_payload.get("job_id") or "unknown"),
        ],
        "credits": _credits(parse_payload),
        "elapsed_seconds": elapsed,
        "settings": {
            "parse_tier": parse_config.tier,
            "parse_version": parse_config.version,
            "parse_expand": list(parse_config.effective_expand()),
            "classify_mode": classify_config.mode,
            "classify_max_pages": classify_config.max_pages,
            "extract_tier": extract_config.tier,
            "extract_parse_tier": extract_config.parse_tier,
            "extract_max_pages": extract_config.max_pages,
        },
        "result_shapes": {
            "parse": sorted(key for key in parse_payload.keys() if key != "markdown"),
            "classify": sorted(classify_payload.keys()),
            "extract": sorted(extract_payload.keys()),
        },
        "warnings": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def _load_secrets_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _ensure_synthetic_source() -> Path:
    path = Path("data/evaluation/llama_first/synthetic_llama_smoke.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            "# Politica SST\n\nCodigo: SST-SMOKE-001\n\nDocumento sintetico no sensible para validar Parse, Classify y Extract.",
            encoding="utf-8",
        )
    return path


def _blocked_result(document_id: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": "blocked-llama-cloud-smoke",
        "status": "blocked",
        "document_id": document_id,
        "capabilities": [],
        "provider_job_ids": [],
        "credits": 0,
        "elapsed_seconds": 0,
        "warnings": [reason],
    }


def _payload(response: object) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if hasattr(response, "dict"):
        return response.dict()
    return {}


def _job_id(payload: dict[str, Any]) -> str:
    job = payload.get("job") if isinstance(payload.get("job"), dict) else {}
    value = payload.get("id") or payload.get("job_id") or job.get("id")
    if not value:
        raise RuntimeError("LlamaParse smoke response did not include a parse job id")
    return str(value)


def _credits(payload: dict[str, Any]) -> int | float:
    metadata = payload.get("job_metadata") if isinstance(payload.get("job_metadata"), dict) else {}
    value = metadata.get("credits") or metadata.get("credits_used") or metadata.get("usage_credits")
    return value if isinstance(value, int | float) else 0


def _smoke_extract_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "document_title": {
                "type": "string",
                "description": "Title or main heading of the document.",
            },
            "document_code": {
                "type": "string",
                "description": "Document code if present, otherwise null.",
            },
        },
        "required": ["document_title"],
    }


def _env_bool(key: str) -> bool:
    return os.environ.get(key, "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
