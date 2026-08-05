from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from ingestion.domain.models.provider import ProviderJobRef
from ingestion.schemas.common import StrictModel


class ParsedPage(StrictModel):
    page_number: int = Field(ge=1)
    markdown: str
    warnings: list[str] = Field(default_factory=list)


class ParsedItemsPage(StrictModel):
    page_number: int = Field(ge=1)
    items: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ParsedPageMetadata(StrictModel):
    page_number: int = Field(ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ParsedDocument(StrictModel):
    provider_job: ProviderJobRef
    markdown_pages: list[ParsedPage]
    items_pages: list[ParsedItemsPage] = Field(default_factory=list)
    page_metadata: list[ParsedPageMetadata] = Field(default_factory=list)
    job_metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_markdown_pages_are_contiguous(self) -> "ParsedDocument":
        page_numbers = [page.page_number for page in self.markdown_pages]
        if page_numbers and page_numbers != list(range(1, len(page_numbers) + 1)):
            raise ValueError("markdown pages must be contiguous from page 1")
        return self
