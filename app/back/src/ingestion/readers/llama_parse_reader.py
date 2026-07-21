from __future__ import annotations

import asyncio
from pathlib import Path

from ingestion.application.ports.parser import ParseRequest
from ingestion.infrastructure.llama_cloud.mappers.read_result_mapper import parsed_document_to_read_result
from ingestion.infrastructure.llama_cloud.parse_adapter import LlamaParseAdapter
from ingestion.readers.base import ReadResult


class LlamaParseReader:
    def __init__(self, *, adapter: LlamaParseAdapter, configuration_hash: str) -> None:
        self._adapter = adapter
        self._configuration_hash = configuration_hash

    def read(self, source_path: Path, *, document_id: str, source_hash: str) -> ReadResult:
        parsed = asyncio.run(
            self._adapter.parse(
                ParseRequest(
                    document_id=document_id,
                    source_path=source_path,
                    source_hash=source_hash,
                    mime_type="application/pdf",
                    configuration_hash=self._configuration_hash,
                )
            )
        )
        return parsed_document_to_read_result(parsed)
