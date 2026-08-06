"""Read persisted chunk bundles without re-chunking them.

``chunk_bundles.artifact_relpath`` points at the ``*.chunking_metadata.json``
produced by the chunking pipeline. The parent and child JSONL files live beside
it. This reader is the single place that turns those artifacts into the neutral
records consumed by Embedding and by bundle-first Indexing.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from pydantic import Field

from embedding.domain.errors import ChunkBundleNotFound
from embedding.domain.models import canonical_json
from ingestion.schemas.common import StrictModel


METADATA_SUFFIX = ".chunking_metadata.json"
PARENT_SUFFIX = ".parent_chunks.jsonl"
CHILD_SUFFIX = ".child_chunks.jsonl"

#: How the embedded string is assembled from a stored child chunk.
EMBEDDING_INPUT_TEMPLATE = "context_prefix\\ntext"


class SourceSpanRecord(StrictModel):
    """Page and character provenance carried by every chunk."""

    page_start: int | None = None
    page_end: int | None = None
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)


class SourceParentChunk(StrictModel):
    """One parent chunk read back from a persisted bundle."""

    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    text: str
    source_span: SourceSpanRecord
    block_ids: list[str] = Field(default_factory=list)


class SourceChildChunk(StrictModel):
    """One child chunk plus the exact string that will be embedded."""

    chunk_id: str = Field(min_length=1)
    parent_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    context_prefix: str = ""
    text: str
    source_span: SourceSpanRecord
    token_count: int = Field(ge=0)

    @property
    def embedding_input(self) -> str:
        """Return the exact text handed to the embedding engine."""

        if not self.context_prefix:
            return self.text
        return f"{self.context_prefix}\n{self.text}".strip()

    @property
    def content_hash(self) -> str:
        """Return the digest of the embedded string, used for alignment checks."""

        return sha256(self.embedding_input.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChunkBundleContent:
    """Parents, children and the fingerprint of the embedded content."""

    parents: tuple[SourceParentChunk, ...]
    children: tuple[SourceChildChunk, ...]
    source_content_fingerprint: str
    corpus_version: str
    document_id: str
    source_relpath: str
    source_hash: str
    normalized_relpath: str


@dataclass(frozen=True)
class FilesystemChunkBundleContentReader:
    """Load chunk bundle content from the chunking artifact root."""

    chunks_root: Path

    def read(self, *, artifact_relpath: str) -> ChunkBundleContent:
        """Return the full content of one persisted chunk bundle.

        Raises:
            ChunkBundleNotFound: When any artifact of the bundle is missing.
        """

        metadata_path = self._resolve(artifact_relpath)
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        base = str(metadata_path)[: -len(METADATA_SUFFIX)]
        parents = tuple(
            SourceParentChunk.model_validate(row)
            for row in self._read_jsonl(Path(base + PARENT_SUFFIX))
        )
        children = tuple(
            SourceChildChunk.model_validate(_child_payload(row))
            for row in self._read_jsonl(Path(base + CHILD_SUFFIX))
        )
        return ChunkBundleContent(
            parents=parents,
            children=children,
            source_content_fingerprint=source_content_fingerprint(children),
            corpus_version=str(payload["corpus_version"]),
            document_id=str(payload["document_id"]),
            source_relpath=str(payload["source_relpath"]),
            source_hash=str(payload["source_hash"]),
            normalized_relpath=str(payload["normalized_relpath"]),
        )

    def _resolve(self, artifact_relpath: str) -> Path:
        candidate = (self.chunks_root / artifact_relpath).resolve()
        root = self.chunks_root.resolve()
        if not candidate.is_relative_to(root):
            raise ChunkBundleNotFound("chunk bundle artifact path escapes the chunks root")
        if not candidate.exists() or not str(candidate).endswith(METADATA_SUFFIX):
            raise ChunkBundleNotFound("chunk bundle metadata artifact is missing")
        return candidate

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, object]]:
        if not path.exists():
            raise ChunkBundleNotFound("chunk bundle jsonl artifact is missing")
        with path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]


def _child_payload(row: dict[str, object]) -> dict[str, object]:
    """Keep only the fields the neutral child record declares."""

    allowed = {
        "chunk_id",
        "parent_id",
        "document_id",
        "profile_id",
        "ordinal",
        "context_prefix",
        "text",
        "source_span",
        "token_count",
    }
    return {key: value for key, value in row.items() if key in allowed}


def source_content_fingerprint(children: tuple[SourceChildChunk, ...]) -> str:
    """Digest the ordered embedded content so any source drift is detected."""

    return sha256(
        canonical_json([child.content_hash for child in children]).encode("utf-8")
    ).hexdigest()
