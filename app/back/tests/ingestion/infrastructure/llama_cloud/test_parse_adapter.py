from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.application.ports.parser import ParseRequest
from ingestion.infrastructure.llama_cloud.parse_adapter import LlamaParseAdapter
from ingestion.infrastructure.llama_cloud.parse_config import LlamaParseConfig


class FakeParsingClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.get_calls: list[dict] = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "id": "job_123",
            "status": "completed",
        }

    async def get(self, job_id: str, **kwargs):
        self.get_calls.append({"job_id": job_id, **kwargs})
        return {
            "job": {"id": job_id, "status": "completed"},
            "markdown": [{"page": 1, "markdown": "# Politica SST"}],
            "items": [{"page": 1, "items": [{"type": "heading", "value": "Politica SST"}]}],
            "metadata": [{"page": 1, "confidence": 0.95}],
            "job_metadata": {"credits": 1},
        }


class FakeClient:
    def __init__(self) -> None:
        self.parsing = FakeParsingClient()


@pytest.mark.anyio
async def test_parse_adapter_submits_file_with_config_and_maps_result(tmp_path) -> None:
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF")
    client = FakeClient()
    adapter = LlamaParseAdapter(client=client, config=LlamaParseConfig())

    parsed = await adapter.parse(
        ParseRequest(
            document_id="doc_123",
            source_path=source,
            source_hash="sha256:source",
            mime_type="application/pdf",
            configuration_hash="sha256:config",
        )
    )

    assert client.parsing.calls[0]["upload_file"] == source
    assert client.parsing.calls[0]["tier"] == "cost_effective"
    assert client.parsing.get_calls[0] == {
        "job_id": "job_123",
        "expand": ["markdown", "items", "metadata", "job_metadata"],
    }
    assert parsed.provider_job.job_id == "job_123"
    assert parsed.markdown_pages[0].markdown == "# Politica SST"
    assert parsed.items_pages[0].items[0]["type"] == "heading"
    assert parsed.job_metadata == {"credits": 1}


def test_parse_adapter_maps_markdown_full_when_markdown_is_not_present() -> None:
    from ingestion.infrastructure.llama_cloud.parse_adapter import (
        map_parse_response_to_parsed_document,
    )

    parsed = map_parse_response_to_parsed_document(
        {
            "job": {"id": "pjb_456", "status": "COMPLETED"},
            "markdown_full": "# Documento\n\nContenido extraido.",
        },
        configuration_hash="sha256:config",
    )

    assert parsed.provider_job.job_id == "pjb_456"
    assert parsed.markdown_pages[0].markdown == "# Documento\n\nContenido extraido."


def test_parse_adapter_maps_sdk_pages_container_shape() -> None:
    from ingestion.infrastructure.llama_cloud.parse_adapter import (
        map_parse_response_to_parsed_document,
    )

    parsed = map_parse_response_to_parsed_document(
        {
            "job": {"id": "pjb_789", "status": "COMPLETED"},
            "markdown": {
                "pages": [
                    {"page": 1, "markdown": "# Pagina 1"},
                    {"page": 2, "markdown": "# Pagina 2"},
                ]
            },
            "metadata": {"pages": [{"page": 1, "width": 612}, {"page": 2, "width": 612}]},
        },
        configuration_hash="sha256:config",
    )

    assert [page.markdown for page in parsed.markdown_pages] == [
        "# Pagina 1",
        "# Pagina 2",
    ]
    assert parsed.page_metadata[1].metadata == {"width": 612}


def test_parse_adapter_maps_sdk_v2_nested_job_id() -> None:
    from ingestion.infrastructure.llama_cloud.parse_adapter import (
        map_parse_response_to_parsed_document,
    )

    parsed = map_parse_response_to_parsed_document(
        {
            "job": {"id": "pjb_123", "status": "COMPLETED"},
            "markdown": [{"page": 1, "markdown": "# Documento"}],
            "job_metadata": {"credits": 3},
        },
        configuration_hash="sha256:config",
    )

    assert parsed.provider_job.job_id == "pjb_123"
    assert parsed.provider_job.status == "completed"
