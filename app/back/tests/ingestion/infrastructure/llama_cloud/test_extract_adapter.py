from __future__ import annotations

import pytest

from ingestion.application.ports.extractor import ExtractionRequest
from ingestion.infrastructure.llama_cloud.extract_adapter import LlamaExtractAdapter
from ingestion.infrastructure.llama_cloud.extract_config import LlamaExtractConfig


class FakeExtractClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "id": "extract_123",
            "status": "COMPLETED",
            "data": {"code": "RG.RH-01-SST"},
            "confidence": {"code": 0.87},
            "evidence": {"code": [{"page_number": 1, "text": "RG.RH-01-SST"}]},
        }


class FakeClient:
    def __init__(self) -> None:
        self.extract = FakeExtractClient()


@pytest.mark.anyio
async def test_extract_adapter_reuses_parse_job_id_and_maps_fields() -> None:
    client = FakeClient()
    adapter = LlamaExtractAdapter(
        client=client,
        config=LlamaExtractConfig(
            schema_name="document_control",
            critical_fields=("code",),
            data_schema={
                "type": "object",
                "properties": {"code": {"type": "string"}},
            },
            max_pages=5,
        ),
    )

    result = await adapter.extract(
        ExtractionRequest(
            document_id="doc_123",
            schema_name="document_control",
            parse_job_id="parse_123",
            configuration_hash="sha256:config",
        )
    )

    assert client.extract.calls[0]["file_input"] == "parse_123"
    assert client.extract.calls[0]["configuration"]["tier"] == "cost_effective"
    assert client.extract.calls[0]["configuration"]["parse_tier"] == "fast"
    assert client.extract.calls[0]["configuration"]["max_pages"] == 5
    assert client.extract.calls[0]["configuration"]["data_schema"]["type"] == "object"
    assert result.provider_job.job_id == "extract_123"
    assert result.provider_job.status == "completed"
    assert result.fields[0].name == "code"
    assert result.fields[0].critical is True
    assert result.fields[0].evidence[0].page_number == 1
