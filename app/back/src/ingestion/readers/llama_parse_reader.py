from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

from ingestion.application.ports.parser import ParseRequest
from ingestion.application.services.llama_orchestrator import LlamaOrchestrator
from ingestion.infrastructure.llama_cloud.mappers.read_result_mapper import parsed_document_to_read_result
from ingestion.infrastructure.llama_cloud.parse_adapter import LlamaParseAdapter
from ingestion.readers.base import ReadResult


class LlamaParseReader:
    def __init__(
        self,
        *,
        adapter: LlamaParseAdapter,
        configuration_hash: str,
        orchestrator: LlamaOrchestrator | None = None,
        async_client: object | None = None,
    ) -> None:
        self._adapter = adapter
        self._configuration_hash = configuration_hash
        self._orchestrator = orchestrator
        self._async_client = async_client

    def read(self, source_path: Path, *, document_id: str, source_hash: str) -> ReadResult:
        return asyncio.run(
            self._read(
                source_path,
                document_id=document_id,
                source_hash=source_hash,
            )
        )

    async def _read(
        self,
        source_path: Path,
        *,
        document_id: str,
        source_hash: str,
    ) -> ReadResult:
        try:
            return await self._read_with_cloud(
                source_path,
                document_id=document_id,
                source_hash=source_hash,
            )
        finally:
            await self._close_async_client()

    async def _read_with_cloud(
        self,
        source_path: Path,
        *,
        document_id: str,
        source_hash: str,
    ) -> ReadResult:
        if self._orchestrator is not None:
            result = await self._orchestrator.run(
                document_id=document_id,
                source_path=source_path,
                source_hash=source_hash,
                mime_type="application/pdf",
            )
            return parsed_document_to_read_result(
                result.parsed,
                result.understanding,
            )
        parsed = await self._adapter.parse(
            ParseRequest(
                document_id=document_id,
                source_path=source_path,
                source_hash=source_hash,
                mime_type="application/pdf",
                configuration_hash=self._configuration_hash,
            )
        )
        return parsed_document_to_read_result(parsed)

    async def _close_async_client(self) -> None:
        if self._async_client is None:
            return
        client = self._async_client
        self._async_client = None
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result
