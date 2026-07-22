from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.application.ports.classifier import ClassificationRequest
from ingestion.infrastructure.llama_cloud.classify_adapter import LlamaClassifyAdapter
from ingestion.infrastructure.llama_cloud.classify_config import LlamaClassifyConfig


class FakeClassifyClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "id": "classify_123",
            "status": "completed",
            "label": "formulario",
            "confidence": 0.91,
            "reasoning": "El documento contiene campos de queja.",
            "evidence": [{"page_number": 1, "text": "Formato de queja"}],
            "candidates": [{"label": "manual", "confidence": 0.2}],
        }


class FakeClient:
    def __init__(self) -> None:
        self.classify = FakeClassifyClient()


@pytest.mark.anyio
async def test_classify_adapter_maps_cloud_result_to_domain_result(tmp_path) -> None:
    source = tmp_path / "form.pdf"
    source.write_bytes(b"%PDF")
    client = FakeClient()
    adapter = LlamaClassifyAdapter(client=client)

    result = await adapter.classify(
        ClassificationRequest(
            document_id="doc_123",
            source_path=source,
            labels=("manual", "formulario"),
            max_pages=5,
            configuration_hash="sha256:config",
        )
    )

    assert client.classify.calls[0]["file_input"] == str(source)
    assert client.classify.calls[0]["configuration"]["mode"] == "FAST"
    assert client.classify.calls[0]["configuration"]["rules"] == [
        {"type": "manual", "description": "Documento instructivo o manual corporativo SST."},
        {"type": "formulario", "description": "Formato, formulario o plantilla con campos diligenciables."},
    ]
    assert client.classify.calls[0]["configuration"]["parsing_configuration"] == {
        "lang": "es",
        "max_pages": 5,
    }
    assert result.provider_job.job_id == "classify_123"
    assert result.selected.label == "formulario"
    assert result.selected.confidence == 0.91
    assert result.selected.evidence[0].text == "Formato de queja"


def test_classify_config_uses_fast_mode_and_page_limit() -> None:
    config = LlamaClassifyConfig(max_pages=3)

    assert config.to_run_configuration(labels=("manual", "formulario")) == {
        "mode": "FAST",
        "rules": [
            {"type": "manual", "description": "Documento instructivo o manual corporativo SST."},
            {"type": "formulario", "description": "Formato, formulario o plantilla con campos diligenciables."},
        ],
        "parsing_configuration": {"lang": "es", "max_pages": 3},
    }


def test_classify_config_rule_descriptions_satisfy_cloud_minimum_length() -> None:
    config = LlamaClassifyConfig()

    rules = config.to_run_configuration(labels=("manual", "otro"))["rules"]

    assert all(len(rule["description"]) >= 10 for rule in rules)


@pytest.mark.anyio
async def test_classify_adapter_prefers_parse_job_id_when_available(tmp_path) -> None:
    source = tmp_path / "form.pdf"
    source.write_bytes(b"%PDF")
    client = FakeClient()
    adapter = LlamaClassifyAdapter(client=client)

    await adapter.classify(
        ClassificationRequest(
            document_id="doc_123",
            source_path=source,
            parse_job_id="pjb_123",
            labels=("manual", "formulario"),
            max_pages=3,
            configuration_hash="sha256:config",
        )
    )

    assert client.classify.calls[0]["file_input"] == "pjb_123"
