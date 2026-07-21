from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ingestion.application.ports.classifier import ClassificationRequest
from ingestion.domain.models.classification import ClassificationCandidate, ClassificationResult
from ingestion.domain.models.provider import ProviderJobRef
from ingestion.infrastructure.llama_cloud.classify_config import LlamaClassifyConfig
from ingestion.schemas.common import Evidence


class LlamaClassifyAdapter:
    def __init__(self, *, client: object, config: LlamaClassifyConfig | None = None) -> None:
        self._client = client
        self._config = config or LlamaClassifyConfig()

    async def classify(self, request: ClassificationRequest) -> ClassificationResult:
        max_pages = request.max_pages or self._config.max_pages
        config = LlamaClassifyConfig(
            mode=self._config.mode,
            language=self._config.language,
            max_pages=max_pages,
        )
        result = await self._client.classify.run(
            file_input=str(request.source_path),
            configuration=config.to_run_configuration(labels=request.labels),
        )
        return map_classify_response_to_result(
            result,
            configuration_hash=request.configuration_hash,
        )


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


def _evidence_list(value: object) -> list[Evidence]:
    if not isinstance(value, list):
        return []
    return [Evidence.model_validate(item) for item in value if isinstance(item, dict)]
