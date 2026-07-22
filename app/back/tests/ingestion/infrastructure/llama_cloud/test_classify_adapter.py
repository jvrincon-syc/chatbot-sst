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
            "status": "COMPLETED",
            "label": "formulario",
            "confidence": 0.91,
            "reasoning": "El documento contiene campos de queja.",
            "evidence": [{"page_number": 1, "text": "Formato de queja"}],
            "candidates": [{"label": "manual", "confidence": 0.2}],
        }


class FakeClient:
    def __init__(self) -> None:
        self.classify = FakeClassifyClient()
        self.beta = FakeBetaClient()


class FakeFilesClient:
    def __init__(self) -> None:
        self.upload_calls: list[dict] = []

    async def upload(self, directory_id: str, **kwargs):
        self.upload_calls.append({"directory_id": directory_id, **kwargs})
        return {
            "id": "directory_file_123",
            "directory_id": directory_id,
            "display_name": "form.pdf",
            "project_id": "project_123",
            "unique_id": "doc_123",
            "file_id": "dfl_123",
        }


class FakeDirectoriesClient:
    def __init__(self) -> None:
        self.create_calls: list[dict] = []
        self.files = FakeFilesClient()

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return {
            "id": "directory_123",
            "name": kwargs["name"],
            "project_id": "project_123",
            "type": kwargs.get("type"),
        }


class FakeBetaClient:
    def __init__(self) -> None:
        self.directories = FakeDirectoriesClient()


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

    assert client.beta.directories.create_calls[0] == {
        "name": "classify-doc_123",
        "type": "ephemeral",
    }
    assert client.beta.directories.files.upload_calls[0] == {
        "directory_id": "directory_123",
        "upload_file": source,
        "display_name": "form.pdf",
        "unique_id": "doc_123",
    }
    assert client.classify.calls[0]["file_input"] == "dfl_123"
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
    assert result.provider_job.status == "completed"
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
    assert client.beta.directories.create_calls == []


@pytest.mark.anyio
async def test_classify_adapter_accepts_existing_file_id_without_upload(tmp_path) -> None:
    source = tmp_path / "form.pdf"
    source.write_bytes(b"%PDF")
    client = FakeClient()
    adapter = LlamaClassifyAdapter(client=client)

    await adapter.classify(
        ClassificationRequest(
            document_id="doc_123",
            source_path=source,
            file_id="dfl_existing",
            labels=("manual", "formulario"),
            max_pages=3,
            configuration_hash="sha256:config",
        )
    )

    assert client.classify.calls[0]["file_input"] == "dfl_existing"
    assert client.beta.directories.create_calls == []


@pytest.mark.anyio
async def test_classify_adapter_reuses_uploaded_file_for_same_document(tmp_path) -> None:
    source = tmp_path / "form.pdf"
    source.write_bytes(b"%PDF")
    client = FakeClient()
    adapter = LlamaClassifyAdapter(client=client)
    request = ClassificationRequest(
        document_id="doc_123",
        source_path=source,
        labels=("manual", "formulario"),
        max_pages=3,
        configuration_hash="sha256:config",
    )

    await adapter.classify(request)
    await adapter.classify(request)

    assert len(client.beta.directories.create_calls) == 1
    assert len(client.beta.directories.files.upload_calls) == 1
    assert [call["file_input"] for call in client.classify.calls] == ["dfl_123", "dfl_123"]
