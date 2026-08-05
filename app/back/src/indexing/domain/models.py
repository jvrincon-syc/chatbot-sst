from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ingestion.schemas.common import RelativePosixPath, StrictModel


DocumentStatus = Literal["processed", "needs_review"]


class NormalizedArtifactRefs(StrictModel):
    markdown: RelativePosixPath
    metadata: RelativePosixPath
    pages: RelativePosixPath
    tables: RelativePosixPath
    forms: RelativePosixPath


class IndexingProfile(StrictModel):
    profile_id: str = Field(min_length=1)
    chunking_version: str = Field(min_length=1)
    embedding_provider: str = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    embedding_dimension: int = Field(gt=0)
    vector_store: str = Field(min_length=1)
    metadata_schema_version: str = Field(min_length=1)


class IndexableDocument(StrictModel):
    document_id: str = Field(min_length=1)
    source_relpath: RelativePosixPath
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_status: DocumentStatus
    artifacts: NormalizedArtifactRefs
    profile: IndexingProfile

    @model_validator(mode="after")
    def validate_artifact_stem(self) -> "IndexableDocument":
        expected_prefix = self.source_relpath.rsplit(".", 1)[0]
        artifact_paths = (
            self.artifacts.markdown,
            self.artifacts.metadata,
            self.artifacts.pages,
            self.artifacts.tables,
            self.artifacts.forms,
        )
        if any(not path.startswith(expected_prefix) for path in artifact_paths):
            raise ValueError("artifact refs must share the source normalized base")
        return self


class IndexingResult(StrictModel):
    document_id: str = Field(min_length=1)
    profile: IndexingProfile
    indexed_parent_nodes: int = Field(ge=0)
    indexed_child_nodes: int = Field(ge=0)
    deleted_stale_nodes: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
