from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ingestion.application.ports.classifier import ClassificationRequest
from ingestion.domain.models.classification import ClassificationCandidate, ClassificationResult
from ingestion.domain.models.provider import ProviderJobRef
from ingestion.infrastructure.llama_cloud.classify_config import LlamaClassifyConfig
from ingestion.infrastructure.llama_cloud.errors import ProviderMalformedResultError
from ingestion.schemas.common import Evidence


class LlamaClassifyAdapter:
    def __init__(self, *, client: object, config: LlamaClassifyConfig | None = None) -> None:
        self._client = client
        self._config = config or LlamaClassifyConfig()
        self._uploaded_file_ids: dict[tuple[str, str], str] = {}

    async def classify(self, request: ClassificationRequest) -> ClassificationResult:
        max_pages = request.max_pages or self._config.max_pages
        config = LlamaClassifyConfig(
            mode=self._config.mode,
            language=self._config.language,
            max_pages=max_pages,
        )
        file_input = await self._resolve_file_input(request)
        result = await self._client.classify.run(
            file_input=file_input,
            configuration=config.to_run_configuration(
                labels=request.labels,
                descriptions=request.label_descriptions,
            ),
        )
        return map_classify_response_to_result(
            result,
            configuration_hash=request.configuration_hash,
        )

    async def _resolve_file_input(self, request: ClassificationRequest) -> str:
        if request.parse_job_id is not None:
            return request.parse_job_id
        if request.file_id is not None:
            return request.file_id

        cache_key = (request.document_id, str(request.source_path.resolve()))
        if cache_key not in self._uploaded_file_ids:
            self._uploaded_file_ids[cache_key] = await self._upload_for_classify(request)
        return self._uploaded_file_ids[cache_key]

    async def _upload_for_classify(self, request: ClassificationRequest) -> str:
        beta = getattr(self._client, "beta", None)
        directories = getattr(beta, "directories", None)
        files = getattr(directories, "files", None)
        if directories is None or files is None:
            raise ValueError("LlamaClassify requires parse_job_id, file_id, or beta directory upload support")

        directory = await directories.create(
            name=f"classify-{request.document_id}",
            type="ephemeral",
        )
        directory_id = _required_payload_id(directory, field="id", context="LlamaClassify directory")
        upload = await files.upload(
            directory_id,
            upload_file=request.source_path,
            display_name=Path(request.source_path).name,
            unique_id=request.document_id,
        )
        payload = _payload(upload)
        file_id = str(payload.get("file_id") or "")
        if not file_id:
            raise ProviderMalformedResultError("LlamaClassify file upload response did not include a file_id")
        return file_id


def map_classify_response_to_result(
    response: object,
    *,
    configuration_hash: str,
) -> ClassificationResult:
    payload = _payload(response)
    now = datetime.now(timezone.utc)
    provider_job = ProviderJobRef(
        provider="llama_cloud",
        capability="classify",
        job_id=str(payload.get("id") or payload.get("job_id") or "unknown"),
        status=str(payload.get("status") or "completed"),
        configuration_hash=configuration_hash,
        created_at=now,
        completed_at=now,
    )
    selected = ClassificationCandidate(
        label=str(payload.get("label") or payload.get("classification") or "otro"),
        confidence=float(payload.get("confidence") or 0.0),
        evidence=_evidence_list(payload.get("evidence")),
        reasoning_summary=payload.get("reasoning") if isinstance(payload.get("reasoning"), str) else None,
    )
    candidates = [
        ClassificationCandidate(
            label=str(candidate.get("label", "")),
            confidence=float(candidate.get("confidence") or 0.0),
            evidence=_evidence_list(candidate.get("evidence")),
        )
        for candidate in payload.get("candidates", [])
        if isinstance(candidate, dict)
    ]
    return ClassificationResult(provider_job=provider_job, selected=selected, candidates=candidates)


def _payload(response: object) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    return {}


def _required_payload_id(response: object, *, field: str, context: str) -> str:
    payload = _payload(response)
    value = str(payload.get(field) or "")
    if not value:
        raise ProviderMalformedResultError(f"{context} response did not include {field}")
    return value


def _evidence_list(value: object) -> list[Evidence]:
    if not isinstance(value, list):
        return []
    return [Evidence.model_validate(item) for item in value if isinstance(item, dict)]
