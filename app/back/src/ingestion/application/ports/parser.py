from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import Field

from ingestion.domain.models.parsed_document import ParsedDocument
from ingestion.schemas.common import StrictModel


class ParseRequest(StrictModel):
    document_id: str = Field(min_length=1)
    source_path: Path
    source_hash: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    configuration_hash: str = Field(min_length=1)


class DocumentParserPort(Protocol):
    async def parse(self, request: ParseRequest) -> ParsedDocument: ...
