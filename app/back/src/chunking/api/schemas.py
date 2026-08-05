from __future__ import annotations

from pydantic import Field

from ingestion.schemas.common import StrictModel


class ChunkingRunRequestSchema(StrictModel):
    scope: str = Field(pattern="^(documents|corpus)$")
    document_ids: list[str] = Field(default_factory=list)
    profile_id: str = Field(min_length=1)
    force: bool = False


class SourceSpanSchema(StrictModel):
    page_start: int | None = None
    page_end: int | None = None
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)


class OverlapSpanSchema(StrictModel):
    token_start: int = Field(ge=0)
    token_end: int = Field(ge=0)


class ChunkingProfileSchema(StrictModel):
    profile_id: str
    child_min_tokens: int = Field(ge=1)
    child_target_tokens: int = Field(ge=1)
    child_max_tokens: int = Field(ge=1)
    overlap_ratio: float = Field(ge=0.0, le=1.0)
    overlap_min_tokens: int = Field(ge=0)
    overlap_max_tokens: int = Field(ge=0)


class LinkSetSchema(StrictModel):
    self: str
    documents: str
    validation: str


class ChunkingRunAcceptedSchema(StrictModel):
    run_id: str
    status: str
    profile_id: str
    requested_documents: int
    completed_documents: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    links: LinkSetSchema


class ChunkingRunDocumentSchema(StrictModel):
    document_id: str
    status: str
    reused: bool
    run_id: str
    normalized_relpath: str


class ChunkingStoredDocumentSchema(StrictModel):
    document_id: str
    normalized_relpath: str
    source_relpath: str
    profile_id: str
    parent_count: int = Field(ge=0)
    child_count: int = Field(ge=0)


class ChunkingRunStatusSchema(ChunkingRunAcceptedSchema):
    pass


class ChunkingValidationSchema(StrictModel):
    run_id: str
    status: str
    documents_checked: int = Field(ge=0)
    errors: int = Field(ge=0)
    warnings: int = Field(ge=0)
    checks: list[dict] = Field(default_factory=list)


class ParentChunkSchema(StrictModel):
    chunk_id: str
    document_id: str
    profile_id: str
    ordinal: int = Field(ge=0)
    text: str
    source_span: SourceSpanSchema
    block_ids: list[str] = Field(default_factory=list)


class ChildChunkSchema(StrictModel):
    chunk_id: str
    document_id: str
    profile_id: str
    parent_id: str
    ordinal: int = Field(ge=0)
    context_prefix: str = ""
    text: str
    source_span: SourceSpanSchema
    token_start: int = Field(ge=0)
    token_end: int = Field(ge=0)
    token_count: int = Field(ge=1)
    overlap_previous_tokens: int = Field(ge=0)
    overlap_next_tokens: int = Field(ge=0)
    overlap_previous_span: OverlapSpanSchema | None = None
    overlap_next_span: OverlapSpanSchema | None = None
    zero_overlap_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PaginatedItemsSchema(StrictModel):
    items: list[ChunkingRunDocumentSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedStoredDocumentsSchema(StrictModel):
    items: list[ChunkingStoredDocumentSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedParentChunksSchema(StrictModel):
    items: list[ParentChunkSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedChildChunksSchema(StrictModel):
    items: list[ChildChunkSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class ErrorBodySchema(StrictModel):
    code: str
    message: str
    run_id: str | None = None
    details: dict[str, object] = Field(default_factory=dict)


class ErrorEnvelopeSchema(StrictModel):
    error: ErrorBodySchema
