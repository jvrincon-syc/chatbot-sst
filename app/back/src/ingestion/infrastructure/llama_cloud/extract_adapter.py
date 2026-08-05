from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ingestion.application.ports.extractor import ExtractionRequest
from ingestion.domain.models.extraction import ExtractionField, ExtractionResult
from ingestion.domain.models.provider import ProviderJobRef
from ingestion.infrastructure.llama_cloud.extract_config import LlamaExtractConfig
from ingestion.infrastructure.llama_cloud.status import coerce_provider_job_status
from ingestion.schemas.common import Evidence


class LlamaExtractAdapter:
    def __init__(self, *, client: object, config: LlamaExtractConfig) -> None:
        self._client = client
        self._config = config

    async def extract(self, request: ExtractionRequest) -> ExtractionResult:
        file_input = request.parse_job_id or request.file_id
        if file_input is None:
            raise ValueError("parse_job_id or file_id is required for LlamaExtract")
        result = await self._client.extract.run(
            file_input=file_input,
            configuration=self._config.to_run_configuration(),
        )
        return map_extract_response_to_result(
            result,
            schema_name=request.schema_name,
            configuration_hash=request.configuration_hash,
            critical_fields=set(self._config.critical_fields),
        )


def map_extract_response_to_result(
    response: object,
    *,
    schema_name: str,
    configuration_hash: str,
    critical_fields: set[str],
) -> ExtractionResult:
    payload = _payload(response)
    now = datetime.now(timezone.utc)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    fields = [
        ExtractionField(
            name=name,
            value=value,
            confidence=confidence.get(name),
            evidence=_evidence_list(evidence.get(name)),
            critical=name in critical_fields,
        )
        for name, value in data.items()
    ]
    return ExtractionResult(
        provider_job=ProviderJobRef(
            provider="llama_cloud",
            capability="extract",
            job_id=str(payload.get("id") or payload.get("job_id") or "unknown"),
            status=coerce_provider_job_status(payload.get("status")),
            configuration_hash=configuration_hash,
            created_at=now,
            completed_at=now,
        ),
        schema_name=schema_name,
        fields=fields,
    )


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
