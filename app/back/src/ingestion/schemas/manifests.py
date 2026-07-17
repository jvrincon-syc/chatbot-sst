from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, model_validator

from ingestion.schemas.common import RelativePosixPath, StrictModel
from ingestion.schemas.inventory import InventoryRecord


DocumentStatus = Literal["pending", "processed", "failed", "needs_review"]
RunDisposition = Literal[
    "processed", "reprocessed", "reused", "failed", "needs_review"
]
Sha256 = str


class ArtifactHash(StrictModel):
    relpath: RelativePosixPath
    sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)


class BundleManifest(StrictModel):
    schema_version: Literal["2.0"]
    document_id: str = Field(min_length=1)
    source_relpath: RelativePosixPath
    source_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_base: RelativePosixPath
    required_artifacts: list[RelativePosixPath]
    artifact_hashes: list[ArtifactHash]
    processing_fingerprint: str = Field(min_length=1)
    document_status: DocumentStatus

    @model_validator(mode="after")
    def validate_artifact_set(self) -> "BundleManifest":
        required = set(self.required_artifacts)
        if len(required) != len(self.required_artifacts):
            raise ValueError("required_artifacts must be unique")
        hashed = {item.relpath for item in self.artifact_hashes}
        if len(hashed) != len(self.artifact_hashes):
            raise ValueError("artifact_hashes relpaths must be unique")
        if required != hashed:
            raise ValueError("artifact hashes must match the required artifact set")
        return self


class InventoryManifest(StrictModel):
    schema_version: Literal["2.0"]
    generated_at: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    identity_version: Literal["relpath-posix-v1"] = "relpath-posix-v1"
    records: list[InventoryRecord]


class RunDocument(StrictModel):
    document_id: str = Field(min_length=1)
    source_relpath: RelativePosixPath
    document_status: DocumentStatus
    disposition: RunDisposition
    warnings: list[str] = Field(default_factory=list)


class RunManifest(StrictModel):
    schema_version: Literal["2.0"]
    run_id: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    fingerprints: dict[str, str]
    summary: dict[str, int]
    documents: list[RunDocument]
    bundles: list[BundleManifest]

    @model_validator(mode="after")
    def validate_summary(self) -> "RunManifest":
        if any(value < 0 for value in self.summary.values()):
            raise ValueError("run summary counts must be non-negative")
        return self


class ReviewItem(StrictModel):
    document_id: str = Field(min_length=1)
    source_relpath: RelativePosixPath
    reasons: list[str] = Field(min_length=1)
    details: list[str] = Field(default_factory=list)


class ReviewManifest(StrictModel):
    schema_version: Literal["2.0"]
    run_id: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)
    items: list[ReviewItem]


class ErrorItem(StrictModel):
    document_id: Optional[str] = None
    source_relpath: Optional[RelativePosixPath] = None
    stage: str = Field(min_length=1)
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False


class ErrorManifest(StrictModel):
    schema_version: Literal["2.0"]
    run_id: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)
    items: list[ErrorItem]
