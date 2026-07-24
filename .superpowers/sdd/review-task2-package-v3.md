# Task 2 review package v3

## Files
app/back/src/chunking/domain/models.py
app/back/src/chunking/application/source_span_resolver.py
app/back/src/chunking/infrastructure/__init__.py
app/back/src/chunking/infrastructure/schema2_source.py
app/back/tests/chunking/unit/test_domain_models.py
app/back/tests/chunking/integration/test_schema2_source.py
.superpowers/sdd/task-2-report.md

## FILE: app/back/src/chunking/domain/models.py
```
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json

from chunking.domain.enums import StructuralBlockKind, ZeroOverlapReason
from chunking.domain.errors import ChunkInvariantError, ChunkingProfileError
from chunking.domain.invariants import (
    require_non_empty,
    require_enum_member,
    require_non_negative,
    require_ordered,
    require_overlap_bounds,
    require_positive,
    require_profile_order,
    require_unique,
)
from chunking.domain.policies import LOCAL_STRUCTURAL_ZERO_OVERLAP_POLICY, ZeroOverlapPolicy


def _stable_id(prefix: str, payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = sha256(serialized.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest}"


@dataclass(frozen=True)
class SourceSpan:
    """Inclusive document provenance for a structural element or chunk."""

    page_start: int
    page_end: int
    char_start: int
    char_end: int

    def __post_init__(self) -> None:
        require_positive(self.page_start, field_name="page_start")
        require_positive(self.page_end, field_name="page_end")
        require_non_negative(self.char_start, field_name="char_start")
        require_non_negative(self.char_end, field_name="char_end")
        require_ordered(
            self.page_start,
            self.page_end,
            start_name="page_start",
            end_name="page_end",
        )
        require_ordered(
            self.char_start,
            self.char_end,
            start_name="char_start",
            end_name="char_end",
        )

    def as_payload(self) -> dict[str, int]:
        """Return a deterministic representation for IDs and fingerprints."""
        return {
            "page_start": self.page_start,
            "page_end": self.page_end,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


@dataclass(frozen=True)
class StructuralBlock:
    """A normalized structural unit with stable source provenance."""

    block_id: str
    document_id: str
    ordinal: int
    kind: StructuralBlockKind
    text: str
    source_span: SourceSpan
    heading_path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_non_empty(self.block_id, field_name="block_id")
        require_non_empty(self.document_id, field_name="document_id")
        require_non_negative(self.ordinal, field_name="ordinal")
        require_enum_member(
            self.kind,
            enum_type=StructuralBlockKind,
            field_name="kind",
        )
        require_non_empty(self.text, field_name="text")
        expected_id = _stable_id(
            "block",
            {
                "document_id": self.document_id,
                "ordinal": self.ordinal,
                "kind": self.kind.value,
                "text": self.text,
                "source_span": self.source_span.as_payload(),
                "heading_path": self.heading_path,
            },
        )
        if self.block_id != expected_id:
            raise ChunkInvariantError("block_id must match content and structural position")

    @classmethod
    def create(
        cls,
        *,
        document_id: str,
        ordinal: int,
        kind: StructuralBlockKind,
        text: str,
        source_span: SourceSpan,
        heading_path: tuple[str, ...] = (),
    ) -> StructuralBlock:
        """Create a block with a deterministic content-and-position identifier."""
        require_non_empty(document_id, field_name="document_id")
        require_non_negative(ordinal, field_name="ordinal")
        require_enum_member(kind, enum_type=StructuralBlockKind, field_name="kind")
        require_non_empty(text, field_name="text")
        block_id = _stable_id(
            "block",
            {
                "document_id": document_id,
                "ordinal": ordinal,
                "kind": kind.value,
                "text": text,
                "source_span": source_span.as_payload(),
                "heading_path": heading_path,
            },
        )
        return cls(block_id, document_id, ordinal, kind, text, source_span, heading_path)


@dataclass(frozen=True)
class PageTrace:
    """Literal page content and its character range in normalized Markdown."""

    page_number: int
    char_start: int
    char_end: int
    text_raw: str
    text_normalized: str

    def __post_init__(self) -> None:
        require_positive(self.page_number, field_name="page_number")
        require_non_negative(self.char_start, field_name="char_start")
        require_non_negative(self.char_end, field_name="char_end")
        require_ordered(
            self.char_start,
            self.char_end,
            start_name="char_start",
            end_name="char_end",
        )


@dataclass(frozen=True)
class ValidatedSidecars:
    """Presence and non-invented OCR provenance from validated sidecars."""

    tables_present: bool = False
    forms_present: bool = False
    ocr_present: bool = False
    ocr_confidence: float | None = None
    table_markdown: tuple[str, ...] = ()
    form_titles: tuple[str, ...] = ()


@dataclass(frozen=True)
class NormalizedDocumentBundle:
    """Pre-structural normalized document consumed before Task 3 block creation."""

    document_id: str
    source_hash: str
    corpus_version: str
    markdown: str
    source_relpath: str = ""
    normalized_relpath: str = ""
    page_traces: tuple[PageTrace, ...] = ()
    sidecars: ValidatedSidecars = field(default_factory=ValidatedSidecars)
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_non_empty(self.document_id, field_name="document_id")
        require_non_empty(self.source_hash, field_name="source_hash")
        require_non_empty(self.corpus_version, field_name="corpus_version")
        require_non_empty(self.markdown, field_name="markdown")


@dataclass(frozen=True)
class ChunkingProfile:
    """Immutable, fingerprinted policy for one structural chunking lane."""

    profile_id: str
    child_min_tokens: int
    child_target_tokens: int
    child_max_tokens: int
    overlap_ratio: float
    overlap_min_tokens: int
    overlap_max_tokens: int
    zero_overlap_reasons: frozenset[ZeroOverlapReason] = field(
        default_factory=lambda: LOCAL_STRUCTURAL_ZERO_OVERLAP_POLICY.allowed_reasons
    )

    def __post_init__(self) -> None:
        require_non_empty(self.profile_id, field_name="profile_id")
        require_positive(self.child_min_tokens, field_name="child_min_tokens")
        require_positive(self.child_target_tokens, field_name="child_target_tokens")
        require_positive(self.child_max_tokens, field_name="child_max_tokens")
        require_profile_order(
            self.child_min_tokens,
            self.child_target_tokens,
            self.child_max_tokens,
        )
        if not 0 <= self.overlap_ratio <= 1:
            raise ChunkingProfileError("overlap_ratio must be between 0 and 1")
        require_non_negative(self.overlap_min_tokens, field_name="overlap_min_tokens")
        require_non_negative(self.overlap_max_tokens, field_name="overlap_max_tokens")
        require_overlap_bounds(
            self.overlap_min_tokens,
            self.overlap_max_tokens,
            self.child_max_tokens,
        )
        if any(
            not isinstance(reason, ZeroOverlapReason)
            for reason in self.zero_overlap_reasons
        ):
            raise ChunkingProfileError(
                "zero_overlap_reasons must contain only valid ZeroOverlapReason values"
            )

    @classmethod
    def local_structural_v1(cls) -> ChunkingProfile:
        """Return the canonical local structural chunking profile."""
        return cls(
            profile_id="local-structural-v1",
            child_min_tokens=250,
            child_target_tokens=350,
            child_max_tokens=450,
            overlap_ratio=0.12,
            overlap_min_tokens=30,
            overlap_max_tokens=60,
            zero_overlap_reasons=LOCAL_STRUCTURAL_ZERO_OVERLAP_POLICY.allowed_reasons,
        )

    @property
    def fingerprint(self) -> str:
        """Return the deterministic identity of all semantic profile settings."""
        return _stable_id(
            "chunking-profile",
            {
                "profile_id": self.profile_id,
                "child_min_tokens": self.child_min_tokens,
                "child_target_tokens": self.child_target_tokens,
                "child_max_tokens": self.child_max_tokens,
                "overlap_ratio": self.overlap_ratio,
                "overlap_min_tokens": self.overlap_min_tokens,
                "overlap_max_tokens": self.overlap_max_tokens,
                "zero_overlap_reasons": sorted(reason.value for reason in self.zero_overlap_reasons),
            },
        )

    def overlap_tokens_for_target(self) -> int:
        """Calculate the bounded overlap count for a target-sized child."""
        requested = round(self.child_target_tokens * self.overlap_ratio)
        return min(self.overlap_max_tokens, max(self.overlap_min_tokens, requested))

    @property
    def zero_overlap_policy(self) -> ZeroOverlapPolicy:
        """Return the policy represented by the profile's explicit exceptions."""
        return ZeroOverlapPolicy(self.zero_overlap_reasons)


@dataclass(frozen=True)
class ParentChunk:
    """A structural parent that groups retrieval-oriented child chunks."""

    chunk_id: str
    document_id: str
    profile_id: str
    ordinal: int
    text: str
    source_span: SourceSpan
    block_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        require_non_empty(self.chunk_id, field_name="chunk_id")
        require_non_empty(self.document_id, field_name="document_id")
        require_non_empty(self.profile_id, field_name="profile_id")
        require_non_negative(self.ordinal, field_name="ordinal")
        require_non_empty(self.text, field_name="text")
        if not self.block_ids:
            raise ChunkInvariantError("block_ids must not be empty")
        require_unique(self.block_ids, field_name="block_ids")
        expected_id = _stable_id(
            "parent",
            {
                "document_id": self.document_id,
                "profile_id": self.profile_id,
                "ordinal": self.ordinal,
                "text": self.text,
                "source_span": self.source_span.as_payload(),
                "block_ids": self.block_ids,
            },
        )
        if self.chunk_id != expected_id:
            raise ChunkInvariantError("chunk_id must match content and structural position")

    def as_payload(self) -> dict[str, object]:
        """Return the complete canonical parent payload for traceability."""
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "profile_id": self.profile_id,
            "ordinal": self.ordinal,
            "text": self.text,
            "source_span": self.source_span.as_payload(),
            "block_ids": list(self.block_ids),
        }

    @classmethod
    def create(
        cls,
        *,
        document_id: str,
        profile_id: str,
        ordinal: int,
        text: str,
        source_span: SourceSpan,
        block_ids: tuple[str, ...],
    ) -> ParentChunk:
        """Create a parent with a deterministic content-and-structure identifier."""
        require_non_empty(document_id, field_name="document_id")
        require_non_empty(profile_id, field_name="profile_id")
        require_non_negative(ordinal, field_name="ordinal")
        require_non_empty(text, field_name="text")
        if not block_ids:
            raise ChunkInvariantError("block_ids must not be empty")
        require_unique(block_ids, field_name="block_ids")
        chunk_id = _stable_id(
            "parent",
            {
                "document_id": document_id,
                "profile_id": profile_id,
                "ordinal": ordinal,
                "text": text,
                "source_span": source_span.as_payload(),
                "block_ids": block_ids,
            },
        )
        return cls(chunk_id, document_id, profile_id, ordinal, text, source_span, block_ids)


@dataclass(frozen=True)
class ChildChunk:
    """A retrieval child that preserves its parent, span, and overlap decision."""

    chunk_id: str
    document_id: str
    profile_id: str
    parent_id: str
    ordinal: int
    text: str
    source_span: SourceSpan
    token_count: int
    overlap_tokens: int
    zero_overlap_reason: ZeroOverlapReason | None

    def __post_init__(self) -> None:
        require_non_empty(self.chunk_id, field_name="chunk_id")
        require_non_empty(self.document_id, field_name="document_id")
        require_non_empty(self.profile_id, field_name="profile_id")
        require_non_empty(self.parent_id, field_name="parent_id")
        require_non_negative(self.ordinal, field_name="ordinal")
        require_non_empty(self.text, field_name="text")
        require_positive(self.token_count, field_name="token_count")
        require_non_negative(self.overlap_tokens, field_name="overlap_tokens")
        if self.zero_overlap_reason is not None:
            require_enum_member(
                self.zero_overlap_reason,
                enum_type=ZeroOverlapReason,
                field_name="zero_overlap_reason",
            )
        if self.overlap_tokens >= self.token_count:
            raise ChunkInvariantError("overlap_tokens must be smaller than token_count")
        if self.overlap_tokens == 0 and self.zero_overlap_reason is None:
            raise ChunkInvariantError("zero_overlap_reason is required when overlap_tokens is zero")
        if self.overlap_tokens > 0 and self.zero_overlap_reason is not None:
            raise ChunkInvariantError("zero_overlap_reason requires overlap_tokens to be zero")
        expected_id = _stable_id(
            "child",
            {
                "document_id": self.document_id,
                "profile_id": self.profile_id,
                "parent_id": self.parent_id,
                "ordinal": self.ordinal,
                "text": self.text,
                "source_span": self.source_span.as_payload(),
            },
        )
        if self.chunk_id != expected_id:
            raise ChunkInvariantError("chunk_id must match content and structural position")

    def as_payload(self) -> dict[str, object]:
        """Return the complete canonical child payload for traceability."""
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "profile_id": self.profile_id,
            "parent_id": self.parent_id,
            "ordinal": self.ordinal,
            "text": self.text,
            "source_span": self.source_span.as_payload(),
            "token_count": self.token_count,
            "overlap_tokens": self.overlap_tokens,
            "zero_overlap_reason": (
                self.zero_overlap_reason.value
                if isinstance(self.zero_overlap_reason, ZeroOverlapReason)
                else None
            ),
        }

    @classmethod
    def create(
        cls,
        *,
        document_id: str,
        profile_id: str,
        parent_id: str,
        ordinal: int,
        text: str,
        source_span: SourceSpan,
        token_count: int,
        overlap_tokens: int,
        zero_overlap_reason: ZeroOverlapReason | None,
    ) -> ChildChunk:
        """Create a child with a deterministic parent-scoped identifier."""
        require_non_empty(document_id, field_name="document_id")
        require_non_empty(profile_id, field_name="profile_id")
        require_non_empty(parent_id, field_name="parent_id")
        require_non_negative(ordinal, field_name="ordinal")
        require_non_empty(text, field_name="text")
        require_positive(token_count, field_name="token_count")
        require_non_negative(overlap_tokens, field_name="overlap_tokens")
        if zero_overlap_reason is not None:
            require_enum_member(
                zero_overlap_reason,
                enum_type=ZeroOverlapReason,
                field_name="zero_overlap_reason",
            )
        if overlap_tokens >= token_count:
            raise ChunkInvariantError("overlap_tokens must be smaller than token_count")
        if overlap_tokens == 0 and zero_overlap_reason is None:
            raise ChunkInvariantError("zero_overlap_reason is required when overlap_tokens is zero")
        if overlap_tokens > 0 and zero_overlap_reason is not None:
            raise ChunkInvariantError("zero_overlap_reason requires overlap_tokens to be zero")
        chunk_id = _stable_id(
            "child",
            {
                "document_id": document_id,
                "profile_id": profile_id,
                "parent_id": parent_id,
                "ordinal": ordinal,
                "text": text,
                "source_span": source_span.as_payload(),
            },
        )
        return cls(
            chunk_id,
            document_id,
            profile_id,
            parent_id,
            ordinal,
            text,
            source_span,
            token_count,
            overlap_tokens,
            zero_overlap_reason,
        )


@dataclass(frozen=True)
class ChunkBundle:
    """Validated parent-child output for a single normalized document."""

    document_id: str
    profile: ChunkingProfile
    parents: tuple[ParentChunk, ...]
    children: tuple[ChildChunk, ...]

    def __post_init__(self) -> None:
        require_non_empty(self.document_id, field_name="document_id")
        if not self.parents:
            raise ChunkInvariantError("parents must not be empty")
        if not self.children:
            raise ChunkInvariantError("children must not be empty")
        require_unique((parent.chunk_id for parent in self.parents), field_name="parent_ids")
        require_unique((child.chunk_id for child in self.children), field_name="child_ids")
        parent_ids = {parent.chunk_id for parent in self.parents}
        if any(parent.document_id != self.document_id for parent in self.parents):
            raise ChunkInvariantError("all parents must belong to document_id")
        if any(parent.profile_id != self.profile.profile_id for parent in self.parents):
            raise ChunkInvariantError("all parents must use profile_id")
        for child in self.children:
            if child.document_id != self.document_id:
                raise ChunkInvariantError("all children must belong to document_id")
            if child.profile_id != self.profile.profile_id:
                raise ChunkInvariantError("all children must use profile_id")
            if child.parent_id not in parent_ids:
                raise ChunkInvariantError("child parent_id must exist in parents")
            if child.zero_overlap_reason is not None and not isinstance(
                child.zero_overlap_reason,
                ZeroOverlapReason,
            ):
                raise ChunkInvariantError(
                    "zero_overlap_reason must be a valid ZeroOverlapReason"
                )
            if child.token_count > self.profile.child_max_tokens:
                raise ChunkInvariantError(
                    "child token_count must not exceed child_max_tokens including overlap"
                )
            if child.overlap_tokens == 0 and not self.profile.zero_overlap_policy.allows(
                child.zero_overlap_reason
            ):
                raise ChunkInvariantError("zero_overlap_reason is not allowed by the profile policy")
            if child.overlap_tokens > 0 and not (
                self.profile.overlap_min_tokens
                <= child.overlap_tokens
                <= self.profile.overlap_max_tokens
            ):
                raise ChunkInvariantError("overlap_tokens must be within profile bounds")

    @property
    def fingerprint(self) -> str:
        """Return a deterministic fingerprint of the complete chunk output."""
        return _stable_id(
            "chunk-bundle",
            {
                "document_id": self.document_id,
                "profile_fingerprint": self.profile.fingerprint,
                "parents": [parent.as_payload() for parent in self.parents],
                "children": [child.as_payload() for child in self.children],
            },
        )

    def as_payload(self) -> dict[str, object]:
        """Return the complete canonical bundle payload for traceability."""
        return {
            "document_id": self.document_id,
            "profile_fingerprint": self.profile.fingerprint,
            "parents": [parent.as_payload() for parent in self.parents],
            "children": [child.as_payload() for child in self.children],
        }

    def validate_against_document(self, document: NormalizedDocumentBundle) -> None:
        """Ensure every parent references structural blocks from the input document."""
        if document.document_id != self.document_id:
            raise ChunkInvariantError("document document_id must match the chunk bundle")


@dataclass(frozen=True)
class ChunkingRun:
    """Traceable result metadata for one deterministic chunking execution."""

    run_id: str
    document_id: str
    profile_fingerprint: str
    bundle_fingerprint: str

    @classmethod
    def create(cls, *, document: NormalizedDocumentBundle, bundle: ChunkBundle) -> ChunkingRun:
        """Create run metadata tied to the document and complete chunk output."""
        if bundle.document_id != document.document_id:
            raise ChunkInvariantError("bundle document_id must match the normalized document")
        bundle.validate_against_document(document)
        profile_fingerprint = bundle.profile.fingerprint
        bundle_fingerprint = bundle.fingerprint
        run_id = _stable_id(
            "chunking-run",
            {
                "document_id": document.document_id,
                "source_hash": document.source_hash,
                "corpus_version": document.corpus_version,
                "profile_fingerprint": profile_fingerprint,
                "bundle_fingerprint": bundle_fingerprint,
                "bundle": bundle.as_payload(),
            },
        )
        return cls(run_id, document.document_id, profile_fingerprint, bundle_fingerprint)
```

## FILE: app/back/src/chunking/application/source_span_resolver.py
```
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from chunking.domain.models import PageTrace
from ingestion.schemas.artifacts import PageRecord


PAGE_TRACE_UNRESOLVED = "PAGE_TRACE_UNRESOLVED"
_PAGE_MARKER_RE = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")


@dataclass(frozen=True)
class PageTraceResolution:
    """Resolved page traces or a fail-closed provenance warning."""

    page_traces: tuple[PageTrace, ...] = ()
    warnings: tuple[str, ...] = ()


class SourceSpanResolver:
    """Resolve Markdown character ranges to source pages without guessing."""

    def resolve(self, *, markdown: str, pages: Sequence[PageRecord]) -> PageTraceResolution:
        """Prefer explicit page markers, then require unique sequential text alignment."""
        source_page_numbers = tuple(page.page_number for page in pages)
        if len(source_page_numbers) != len(set(source_page_numbers)):
            return PageTraceResolution(warnings=(PAGE_TRACE_UNRESOLVED,))
        marker_resolution = self._resolve_markers(markdown=markdown, pages=pages)
        if marker_resolution is not None:
            return marker_resolution

        aligned_traces = self._resolve_alignment(markdown=markdown, pages=pages)
        if aligned_traces is not None:
            return PageTraceResolution(page_traces=aligned_traces)

        return PageTraceResolution(warnings=(PAGE_TRACE_UNRESOLVED,))

    def _resolve_markers(
        self, *, markdown: str, pages: Sequence[PageRecord]
    ) -> PageTraceResolution | None:
        matches = tuple(_PAGE_MARKER_RE.finditer(markdown))
        if not matches:
            return None
        page_numbers = tuple(int(match.group(1)) for match in matches)
        if len(page_numbers) != len(set(page_numbers)):
            return PageTraceResolution(warnings=(PAGE_TRACE_UNRESOLVED,))

        page_by_number = {page.page_number: page for page in pages}
        if any(page_number not in page_by_number for page_number in page_numbers):
            return PageTraceResolution(warnings=(PAGE_TRACE_UNRESOLVED,))
        traces: list[PageTrace] = []
        for index, match in enumerate(matches):
            page_number = page_numbers[index]
            page = page_by_number[page_number]
            next_start = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
            traces.append(
                PageTrace(
                    page_number=page_number,
                    char_start=match.start(),
                    char_end=next_start,
                    text_raw=page.text_raw,
                    text_normalized=page.text_normalized,
                )
            )
        return PageTraceResolution(page_traces=tuple(traces))

    def _resolve_alignment(
        self, *, markdown: str, pages: Sequence[PageRecord]
    ) -> tuple[PageTrace, ...] | None:
        if not pages:
            return None
        traces: list[PageTrace] = []
        search_start = 0
        for page in pages:
            text = page.text_normalized
            if not text:
                return None
            position = markdown.find(text, search_start)
            if position < 0 or markdown.find(text, position + 1) >= 0:
                return None
            end = position + len(text)
            traces.append(
                PageTrace(
                    page_number=page.page_number,
                    char_start=position,
                    char_end=end,
                    text_raw=page.text_raw,
                    text_normalized=page.text_normalized,
                )
            )
            search_start = end
        return tuple(traces)
```

## FILE: app/back/src/chunking/infrastructure/__init__.py
```
"""Filesystem adapters for chunking inputs."""
```

## FILE: app/back/src/chunking/infrastructure/schema2_source.py
```
from __future__ import annotations

import json
import re
from pathlib import Path

from chunking.application.source_span_resolver import SourceSpanResolver
from chunking.domain.models import NormalizedDocumentBundle, ValidatedSidecars
from ingestion.schemas.artifacts import (
    FormsArtifact,
    MetadataArtifact,
    OcrArtifact,
    PagesArtifact,
    TablesArtifact,
)
from ingestion.schemas.loader import load_artifact


_FRONT_MATTER_RE = re.compile(r"\A---\r?\n(?P<content>.*?)\r?\n---\r?\n?", re.DOTALL)


class Schema2NormalizedDocumentSource:
    """Loads a validated Schema 2 bundle rooted in ``docs_normalized``."""

    def __init__(self, docs_normalized: Path, resolver: SourceSpanResolver | None = None) -> None:
        """Create a source constrained to one normalized-document root."""
        self._docs_normalized = docs_normalized.resolve()
        self._resolver = resolver or SourceSpanResolver()

    def load(self, relative_markdown_path: str | Path) -> NormalizedDocumentBundle:
        """Return a pre-structural bundle after validating all available sidecars."""
        markdown_path = self._resolve_markdown_path(relative_markdown_path)
        markdown = markdown_path.read_text(encoding="utf-8")
        metadata = self._load_required(markdown_path, "metadata", MetadataArtifact)
        pages = self._load_required(markdown_path, "pages", PagesArtifact)
        tables = self._load_optional(markdown_path, "tables", TablesArtifact)
        forms = self._load_optional(markdown_path, "forms", FormsArtifact)
        ocr = self._load_optional(markdown_path, "ocr", OcrArtifact)

        relative_path = markdown_path.relative_to(self._docs_normalized).as_posix()
        self._validate_consistency(
            markdown=markdown,
            relative_path=relative_path,
            metadata=metadata,
            pages=pages,
            tables=tables,
            forms=forms,
            ocr=ocr,
        )
        resolution = self._resolver.resolve(markdown=markdown, pages=pages.pages)
        return NormalizedDocumentBundle(
            document_id=metadata.document_id,
            source_hash=metadata.source_hash,
            corpus_version=metadata.corpus_version,
            markdown=markdown,
            source_relpath=str(metadata.source_relpath),
            normalized_relpath=str(metadata.normalized_relpath),
            page_traces=resolution.page_traces,
            sidecars=ValidatedSidecars(
                tables_present=tables is not None,
                forms_present=forms is not None,
                ocr_present=ocr is not None,
                ocr_confidence=ocr.document_confidence.value if ocr is not None else None,
                table_markdown=(
                    tuple(table.markdown_representation for table in tables.tables)
                    if tables is not None
                    else ()
                ),
                form_titles=(
                    tuple(group.title for group in forms.groups if group.title is not None)
                    if forms is not None
                    else ()
                ),
            ),
            warnings=resolution.warnings,
        )

    def _resolve_markdown_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            candidate = path.resolve()
            if not candidate.is_relative_to(self._docs_normalized):
                raise ValueError("markdown path is outside docs_normalized")
            return candidate
        if any(part in {"", ".", ".."} for part in path.parts) or path.suffix != ".md":
            raise ValueError("markdown path contains an unsafe component")
        candidate = (self._docs_normalized / path).resolve()
        if not candidate.is_relative_to(self._docs_normalized):
            raise ValueError("markdown path is outside docs_normalized")
        return candidate

    def _load_required(self, markdown_path: Path, name: str, artifact_type: type[object]):
        path = self._resolve_sidecar_path(markdown_path, name)
        if not path.is_file():
            raise ValueError(f"required {name} sidecar is missing")
        return self._load(path, artifact_type)

    def _load_optional(self, markdown_path: Path, name: str, artifact_type: type[object]):
        path = self._resolve_sidecar_path(markdown_path, name)
        return self._load(path, artifact_type) if path.is_file() else None

    def _resolve_sidecar_path(self, markdown_path: Path, name: str) -> Path:
        path = markdown_path.with_suffix(f".{name}.json").resolve()
        if not path.is_relative_to(self._docs_normalized):
            raise ValueError(f"{name} sidecar is outside docs_normalized")
        return path

    def _load(self, path: Path, artifact_type: type[object]):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON sidecar: {path.name}") from error
        return load_artifact(payload, artifact_type)

    def _validate_consistency(
        self,
        *,
        markdown: str,
        relative_path: str,
        metadata: MetadataArtifact,
        pages: PagesArtifact,
        tables: TablesArtifact | None,
        forms: FormsArtifact | None,
        ocr: OcrArtifact | None,
    ) -> None:
        if str(metadata.normalized_relpath) != relative_path:
            raise ValueError("metadata normalized_relpath does not match markdown path")
        if metadata.page_count != pages.page_count:
            raise ValueError("metadata page_count does not match pages page_count")
        document_ids = [metadata.document_id, pages.document_id]
        document_ids.extend(sidecar.document_id for sidecar in (tables, forms, ocr) if sidecar is not None)
        if any(document_id != metadata.document_id for document_id in document_ids):
            raise ValueError("sidecar document_id does not match metadata document_id")

        front_matter = self._front_matter(markdown)
        for key, expected in (
            ("document_id", metadata.document_id),
            ("source_relpath", str(metadata.source_relpath)),
            ("source_hash", metadata.source_hash),
        ):
            value = front_matter.get(key)
            if value is not None and value != expected:
                raise ValueError(f"markdown {key} does not match metadata")

    def _front_matter(self, markdown: str) -> dict[str, str]:
        match = _FRONT_MATTER_RE.match(markdown)
        if match is None:
            return {}
        values: dict[str, str] = {}
        for line in match.group("content").splitlines():
            key, separator, value = line.partition(":")
            if separator:
                values[key.strip()] = value.strip()
        return values
```

## FILE: app/back/tests/chunking/unit/test_domain_models.py
```
from __future__ import annotations

from dataclasses import replace

import pytest

from chunking.domain.enums import StructuralBlockKind, ZeroOverlapReason
from chunking.domain.errors import ChunkInvariantError, ChunkingProfileError
from chunking.domain.models import (
    ChildChunk,
    ChunkBundle,
    ChunkingProfile,
    ChunkingRun,
    NormalizedDocumentBundle,
    ParentChunk,
    SourceSpan,
    StructuralBlock,
)
from chunking.domain.policies import ZeroOverlapPolicy


def _profile(**changes: object) -> ChunkingProfile:
    values: dict[str, object] = {
        "profile_id": "local-structural-v1",
        "child_min_tokens": 250,
        "child_target_tokens": 350,
        "child_max_tokens": 450,
        "overlap_ratio": 0.12,
        "overlap_min_tokens": 30,
        "overlap_max_tokens": 60,
        "zero_overlap_reasons": frozenset(
            {
                ZeroOverlapReason.DOCUMENT_START,
                ZeroOverlapReason.TABLE_OR_FORM_BOUNDARY,
            }
        ),
    }
    values.update(changes)
    return ChunkingProfile(**values)


def _span(**changes: object) -> SourceSpan:
    values: dict[str, object] = {
        "page_start": 1,
        "page_end": 1,
        "char_start": 0,
        "char_end": 18,
    }
    values.update(changes)
    return SourceSpan(**values)


def _parent() -> ParentChunk:
    return ParentChunk.create(
        document_id="doc-1",
        profile_id="local-structural-v1",
        ordinal=0,
        text="Procedimiento seguro",
        source_span=_span(),
        block_ids=("block-1",),
    )


def _child(**changes: object) -> ChildChunk:
    values: dict[str, object] = {
        "document_id": "doc-1",
        "profile_id": "local-structural-v1",
        "parent_id": _parent().chunk_id,
        "ordinal": 0,
        "text": "Procedimiento seguro",
        "source_span": _span(),
        "token_count": 3,
        "overlap_tokens": 0,
        "zero_overlap_reason": ZeroOverlapReason.DOCUMENT_START,
    }
    values.update(changes)
    return ChildChunk.create(**values)


def _document_with_parent() -> tuple[NormalizedDocumentBundle, ParentChunk]:
    document = NormalizedDocumentBundle(
        document_id="doc-1",
        source_hash="source-hash",
        corpus_version="corpus-v1",
        markdown="Procedimiento seguro",
    )
    parent = ParentChunk.create(
        document_id="doc-1",
        profile_id="local-structural-v1",
        ordinal=0,
        text="Procedimiento seguro",
        source_span=_span(),
        block_ids=("block-from-task-3",),
    )
    return document, parent


def _overlapped_child(parent: ParentChunk, **changes: object) -> ChildChunk:
    values: dict[str, object] = {
        "document_id": "doc-1",
        "profile_id": "local-structural-v1",
        "parent_id": parent.chunk_id,
        "ordinal": 0,
        "text": "Procedimiento seguro",
        "source_span": _span(),
        "token_count": 100,
        "overlap_tokens": 30,
        "zero_overlap_reason": None,
    }
    values.update(changes)
    return ChildChunk.create(**values)


def test_rechaza_child_cuando_parent_no_existe() -> None:
    child = _child(parent_id="missing-parent")

    with pytest.raises(ChunkInvariantError, match="parent"):
        ChunkBundle(
            document_id="doc-1",
            profile=_profile(),
            parents=(_parent(),),
            children=(child,),
        )


def test_rechaza_overlap_cuando_supera_el_child() -> None:
    with pytest.raises(ChunkInvariantError, match="overlap"):
        _child(overlap_tokens=4, token_count=3, zero_overlap_reason=None)


def test_rechaza_child_cuyo_total_incluido_overlap_supera_el_maximo() -> None:
    profile = _profile()
    child = _child(token_count=451)

    with pytest.raises(ChunkInvariantError, match="child_max_tokens"):
        ChunkBundle(
            document_id="doc-1",
            profile=profile,
            parents=(_parent(),),
            children=(child,),
        )


def test_rechaza_perfil_cuando_minimo_objetivo_y_maximo_son_incoherentes() -> None:
    with pytest.raises(ChunkingProfileError, match="child_min_tokens"):
        _profile(child_min_tokens=351)


def test_rechaza_perfil_cuando_limites_de_overlap_son_incoherentes() -> None:
    with pytest.raises(ChunkingProfileError, match="overlap_min_tokens"):
        _profile(overlap_min_tokens=61)


def test_perfil_local_define_ratio_y_limites_de_overlap() -> None:
    profile = ChunkingProfile.local_structural_v1()

    assert profile.profile_id == "local-structural-v1"
    assert profile.child_min_tokens == 250
    assert profile.child_target_tokens == 350
    assert profile.child_max_tokens == 450
    assert profile.overlap_ratio == 0.12
    assert profile.overlap_min_tokens == 30
    assert profile.overlap_max_tokens == 60
    assert profile.overlap_tokens_for_target() == 42


def test_rechaza_page_range_cuando_end_es_menor() -> None:
    with pytest.raises(ChunkInvariantError, match="page_end"):
        _span(page_start=2, page_end=1)


def test_rechaza_rangos_negativos_y_chunks_vacios() -> None:
    with pytest.raises(ChunkInvariantError, match="char_start"):
        _span(char_start=-1)

    with pytest.raises(ChunkInvariantError, match="text"):
        StructuralBlock.create(
            document_id="doc-1",
            ordinal=0,
            kind=StructuralBlockKind.PARAGRAPH,
            text="   ",
            source_span=_span(),
        )

    with pytest.raises(ChunkInvariantError, match="text"):
        ParentChunk(
            chunk_id="parent-manual",
            document_id="doc-1",
            profile_id="local-structural-v1",
            ordinal=0,
            text=" ",
            source_span=_span(),
            block_ids=("block-1",),
        )


def test_rechaza_overlap_cero_sin_excepcion_semantica_permitida() -> None:
    with pytest.raises(ChunkInvariantError, match="zero_overlap_reason"):
        _child(zero_overlap_reason=None)

    with pytest.raises(ChunkInvariantError, match="not allowed"):
        ChunkBundle(
            document_id="doc-1",
            profile=_profile(),
            parents=(_parent(),),
            children=(_child(zero_overlap_reason=ZeroOverlapReason.SECTION_BOUNDARY),),
        )


def test_genera_ids_iguales_cuando_entrada_y_perfil_no_cambian() -> None:
    first = ParentChunk.create(
        document_id="doc-1",
        profile_id="local-structural-v1",
        ordinal=0,
        text="Procedimiento seguro",
        source_span=_span(),
        block_ids=("block-1",),
    )
    second = ParentChunk.create(
        document_id="doc-1",
        profile_id="local-structural-v1",
        ordinal=0,
        text="Procedimiento seguro",
        source_span=_span(),
        block_ids=("block-1",),
    )

    assert first.chunk_id == second.chunk_id
    assert first.chunk_id.startswith("parent-")


def test_rechaza_id_que_no_corresponde_al_contenido_y_posicion() -> None:
    with pytest.raises(ChunkInvariantError, match="chunk_id"):
        ParentChunk(
            chunk_id="parent-injected",
            document_id="doc-1",
            profile_id="local-structural-v1",
            ordinal=0,
            text="Procedimiento seguro",
            source_span=_span(),
            block_ids=("block-1",),
        )


def test_cambia_fingerprint_cuando_cambia_overlap() -> None:
    base = _profile()
    changed = _profile(overlap_ratio=0.10)

    assert base.fingerprint != changed.fingerprint


def test_cambia_fingerprint_de_bundle_y_run_cuando_cambia_el_solapamiento() -> None:
    document, parent = _document_with_parent()
    first = ChunkBundle(
        document_id=document.document_id,
        profile=_profile(),
        parents=(parent,),
        children=(_overlapped_child(parent),),
    )
    second = ChunkBundle(
        document_id=document.document_id,
        profile=_profile(),
        parents=(parent,),
        children=(_overlapped_child(parent, token_count=101, overlap_tokens=31),),
    )

    assert first.children[0].chunk_id == second.children[0].chunk_id
    assert first.fingerprint != second.fingerprint
    assert ChunkingRun.create(document=document, bundle=first).run_id != ChunkingRun.create(
        document=document,
        bundle=second,
    ).run_id


def test_chunking_run_does_not_treat_prestructural_bundle_as_block_container() -> None:
    document, _ = _document_with_parent()
    parent = ParentChunk.create(
        document_id=document.document_id,
        profile_id="local-structural-v1",
        ordinal=0,
        text="Procedimiento seguro",
        source_span=_span(),
        block_ids=("missing-block",),
    )
    bundle = ChunkBundle(
        document_id=document.document_id,
        profile=_profile(),
        parents=(parent,),
        children=(_overlapped_child(parent),),
    )

    assert ChunkingRun.create(document=document, bundle=bundle).document_id == document.document_id


def test_rechaza_valores_de_enum_invalidos_en_runtime() -> None:
    with pytest.raises(ChunkInvariantError, match="kind"):
        StructuralBlock.create(
            document_id="doc-1",
            ordinal=0,
            kind="paragraph",  # type: ignore[arg-type]
            text="Procedimiento seguro",
            source_span=_span(),
        )

    with pytest.raises(ChunkingProfileError, match="zero_overlap_reasons"):
        _profile(zero_overlap_reasons=frozenset({"not-a-reason"}))

    with pytest.raises(ChunkInvariantError, match="allowed_reasons"):
        ZeroOverlapPolicy(frozenset({"not-a-reason"}))


def test_rechaza_zero_overlap_reason_invalido_al_construir_child() -> None:
    with pytest.raises(ChunkInvariantError, match="zero_overlap_reason"):
        _child(zero_overlap_reason="not-a-reason")

    with pytest.raises(ChunkInvariantError, match="zero_overlap_reason"):
        replace(_child(), zero_overlap_reason="not-a-reason")
```

## FILE: app/back/tests/chunking/integration/test_schema2_source.py
```
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chunking.infrastructure.schema2_source import Schema2NormalizedDocumentSource


DOCUMENT_ID = "doc_schema2_source"
SOURCE_HASH = "a" * 64
RELATIVE_PATH = "manuales/procedimiento.md"


def _confidence() -> dict[str, object]:
    return {
        "kind": "unavailable",
        "value": None,
        "unit": None,
        "method": None,
        "engine": None,
        "engine_version": None,
        "sample_size": None,
        "provenance": None,
        "warnings": [],
    }


def _observation() -> dict[str, object]:
    return {
        "status": "not_evaluated",
        "value": None,
        "method": None,
        "engine": None,
        "engine_version": None,
        "evidence": [],
        "warnings": [],
    }


def _metadata() -> dict[str, object]:
    document_field = {
        "value": None,
        "value_raw": None,
        "status": "not_found",
        "evidence": [],
        "warnings": [],
    }
    return {
        "schema_version": "2.0",
        "document_id": DOCUMENT_ID,
        "document_name": "procedimiento.md",
        "source_relpath": RELATIVE_PATH,
        "normalized_relpath": RELATIVE_PATH,
        "document_control": {
            "title": document_field,
            "code": document_field,
            "version": document_field,
            "publication_date": document_field,
            "effective_date": document_field,
        },
        "classification": {
            "document_type": "procedimiento",
            "document_type_confidence": _confidence(),
            "topic": "SST",
            "topic_confidence": _confidence(),
        },
        "page_count": 2,
        "extraction_method": "markdown",
        "ocr_confidence": _confidence(),
        "handwriting": _observation(),
        "tables": _observation(),
        "forms": _observation(),
        "source_hash": SOURCE_HASH,
        "corpus_version": "corpus-v2",
        "pipeline_version": "2.0.0",
        "processing_status": "processed",
    }


def _pages(
    *,
    first_text: str = "Codigo SST-01",
    second_text: str = "Fecha 2026-07-23",
    page_numbers: tuple[int, int] = (1, 2),
) -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "document_id": DOCUMENT_ID,
        "page_count": 2,
        "pages": [
            {
                "page_number": page_numbers[0],
                "text_raw": first_text,
                "text_normalized": first_text,
                "extraction_method": "markdown",
                "blocks": [],
                "ocr_confidence": _confidence(),
            },
            {
                "page_number": page_numbers[1],
                "text_raw": second_text,
                "text_normalized": second_text,
                "extraction_method": "markdown",
                "blocks": [],
                "ocr_confidence": _confidence(),
            },
        ],
    }


def _write_bundle(
    root: Path,
    *,
    markdown: str,
    pages: dict[str, object] | None = None,
    metadata: dict[str, object] | None = None,
    optional_sidecars: tuple[str, ...] = (),
) -> Path:
    markdown_path = root / RELATIVE_PATH
    markdown_path.parent.mkdir(parents=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    markdown_path.with_suffix(".metadata.json").write_text(
        json.dumps(metadata or _metadata()), encoding="utf-8"
    )
    markdown_path.with_suffix(".pages.json").write_text(
        json.dumps(pages or _pages()), encoding="utf-8"
    )
    for artifact_name in optional_sidecars:
        payload: dict[str, object] = {
            "schema_version": "2.0",
            "document_id": DOCUMENT_ID,
        }
        if artifact_name == "tables":
            payload.update({"table_count": 0, "tables": []})
        elif artifact_name == "forms":
            payload["groups"] = []
        elif artifact_name == "ocr":
            payload.update({"document_confidence": _confidence(), "pages": []})
        else:
            raise AssertionError(f"unsupported sidecar: {artifact_name}")
        markdown_path.with_suffix(f".{artifact_name}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    return markdown_path


def test_loads_complete_sidecars_and_prefers_markdown_page_markers(tmp_path: Path) -> None:
    markdown = (
        "---\n"
        f"document_id: {DOCUMENT_ID}\n"
        f"source_relpath: {RELATIVE_PATH}\n"
        f"source_hash: {SOURCE_HASH}\n"
        "---\n"
        "<!-- page: 4 -->\nCodigo SST-01\n"
        "<!-- page: 9 -->\nFecha 2026-07-23\n"
    )
    _write_bundle(
        tmp_path,
        markdown=markdown,
        pages=_pages(page_numbers=(4, 9)),
        optional_sidecars=("tables", "forms", "ocr"),
    )
    markdown_path = tmp_path / RELATIVE_PATH
    markdown_path.with_suffix(".tables.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "document_id": DOCUMENT_ID,
                "table_count": 1,
                "tables": [
                    {
                        "table_id": "table-1",
                        "page_number": 4,
                        "bbox": None,
                            "markdown_representation": "| Codigo |\n| SST-01 |",
                        "extractor": "markdown",
                        "quality": _confidence(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    markdown_path.with_suffix(".forms.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "document_id": DOCUMENT_ID,
                "groups": [
                    {
                        "group_id": "form-1",
                        "page_number": 9,
                        "title": "Aprobacion",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    document = Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)

    assert document.markdown == markdown
    assert not hasattr(document, "structural_blocks")
    assert [trace.page_number for trace in document.page_traces] == [4, 9]
    assert document.page_traces[0].text_normalized == "Codigo SST-01"
    assert document.sidecars.tables_present is True
    assert document.sidecars.forms_present is True
    assert document.sidecars.ocr_present is True
    assert document.sidecars.table_markdown == ("| Codigo |\n| SST-01 |",)
    assert document.sidecars.form_titles == ("Aprobacion",)
    assert document.warnings == ()


def test_loads_incomplete_and_absent_optional_sidecars_without_inventing_values(tmp_path: Path) -> None:
    markdown = "Codigo SST-01\n\nFecha 2026-07-23\n"
    _write_bundle(tmp_path, markdown=markdown, optional_sidecars=("forms",))

    document = Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)

    assert [trace.page_number for trace in document.page_traces] == [1, 2]
    assert document.sidecars.tables_present is False
    assert document.sidecars.forms_present is True
    assert document.sidecars.ocr_present is False
    assert document.sidecars.ocr_confidence is None
    assert not hasattr(document, "structural_blocks")


def test_emits_unresolved_warning_when_pages_cannot_be_safely_aligned(tmp_path: Path) -> None:
    _write_bundle(
        tmp_path,
        markdown="Contenido que no coincide con las paginas\n",
        pages=_pages(first_text="Primera pagina", second_text="Segunda pagina"),
    )

    document = Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)

    assert document.page_traces == ()
    assert document.warnings == ("PAGE_TRACE_UNRESOLVED",)


def test_emits_unresolved_warning_for_marker_page_absent_from_pages_sidecar(tmp_path: Path) -> None:
    _write_bundle(
        tmp_path,
        markdown=(
            "<!-- page: 3 -->\nCodigo SST-01\n"
            "<!-- page: 4 -->\nFecha 2026-07-23\n"
        ),
    )

    document = Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)

    assert document.page_traces == ()
    assert document.warnings == ("PAGE_TRACE_UNRESOLVED",)


def test_emits_unresolved_warning_for_duplicate_page_numbers_in_pages_sidecar(tmp_path: Path) -> None:
    _write_bundle(
        tmp_path,
        markdown="<!-- page: 1 -->\nCodigo SST-01\n",
        pages=_pages(page_numbers=(1, 1)),
    )

    document = Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)

    assert document.page_traces == ()
    assert document.warnings == ("PAGE_TRACE_UNRESOLVED",)


def test_rejects_metadata_and_pages_sidecars_with_different_page_counts(tmp_path: Path) -> None:
    metadata = _metadata()
    metadata["page_count"] = 1
    _write_bundle(tmp_path, markdown="Codigo SST-01\n\nFecha 2026-07-23\n", metadata=metadata)

    with pytest.raises(ValueError, match="page_count"):
        Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)


def test_rejects_sidecar_symlink_that_escapes_normalized_root(tmp_path: Path) -> None:
    markdown_path = _write_bundle(tmp_path, markdown="Codigo SST-01\n\nFecha 2026-07-23\n")
    outside_sidecar = tmp_path.parent / "outside.metadata.json"
    outside_sidecar.write_text(json.dumps(_metadata()), encoding="utf-8")
    metadata_path = markdown_path.with_suffix(".metadata.json")
    metadata_path.unlink()
    try:
        metadata_path.symlink_to(outside_sidecar)
    except OSError as error:
        pytest.skip(f"symlinks are unavailable in this test environment: {error}")

    with pytest.raises(ValueError, match="outside docs_normalized"):
        Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)


@pytest.mark.parametrize(
    ("path", "expected_error"),
    [
        ("../procedimiento.md", "unsafe"),
        ("manuales/../../procedimiento.md", "unsafe"),
    ],
)
def test_rejects_path_traversal(tmp_path: Path, path: str, expected_error: str) -> None:
    with pytest.raises(ValueError, match=expected_error):
        Schema2NormalizedDocumentSource(tmp_path).load(path)


def test_rejects_document_outside_normalized_root_and_inconsistent_identity(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    _write_bundle(tmp_path, markdown="<!-- page: 1 -->\nCodigo SST-01\n")
    bad_pages = _pages()
    bad_pages["document_id"] = "doc_other"
    (tmp_path / RELATIVE_PATH).with_suffix(".pages.json").write_text(
        json.dumps(bad_pages), encoding="utf-8"
    )

    source = Schema2NormalizedDocumentSource(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        source.load(outside)
    with pytest.raises(ValueError, match="document_id"):
        source.load(RELATIVE_PATH)
```

## FILE: .superpowers/sdd/task-2-report.md
```
# Task 2 Report: Schema 2 Normalized Source

## Status

Completed without a commit.

## Delivered

- Added `Schema2NormalizedDocumentSource`, rooted to `docs_normalized`, to load
  Markdown and validate Schema 2 metadata, pages, tables, forms, and OCR
  sidecars through the existing `ingestion.schemas.loader.load_artifact`.
- Required Markdown, metadata, and pages sidecars are fail-closed. Tables,
  forms, and OCR are optional and may be present independently.
- Reworked `NormalizedDocumentBundle` into the pre-structural contract needed
  for Task 2/3: literal Markdown, source/page traces, validated sidecar data,
  and warnings. It no longer contains `StructuralBlock` instances.
- Added `SourceSpanResolver`, which prefers Markdown `<!-- page: N -->`
  markers, uses ordered unique `pages.json.text_normalized` alignment only as
  a fallback, and emits `PAGE_TRACE_UNRESOLVED` when neither is safe.
- Added validation for root confinement, traversal attempts, normalized path,
  sidecar `document_id`, and any identifying front-matter values that are
  present (`document_id`, `source_relpath`, `source_hash`).
- Preserved literal Markdown, page raw/normalized text, table Markdown, and
  form titles. OCR confidence is `None` when its sidecar is absent; no value
  or structural block is invented.

## TDD Evidence

1. Added the integration tests before the infrastructure adapter existed.
2. RED run: collection failed with `ModuleNotFoundError: chunking.infrastructure`,
   confirming the test exercised the absent feature.
3. Implemented the minimal source loader and resolver.
4. Added a second RED assertion for retaining validated table/form values;
   it failed because `ValidatedSidecars` lacked `table_markdown`.
5. Added the minimal domain mapping and confirmed GREEN.

## Verification

Required command:

```powershell
$env:TMP=(Resolve-Path '.').Path + '\pytest-temp'; $env:TEMP=$env:TMP; New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null; .\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/integration/test_schema2_source.py -q --basetemp .\pytest-basetemp-task2
```

Result: `6 passed in 0.13s`.

Additional regression:

```powershell
.\.venv_windows_trabajo\Scripts\python.exe -m compileall -q app\back\src\chunking
.\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_domain_models.py app/back/tests/chunking/integration/test_schema2_source.py -q --basetemp .\pytest-basetemp-task2-regression
```

Result: compilation passed and `22 passed in 0.14s`.

## Files Changed

- `app/back/src/chunking/application/source_span_resolver.py`
- `app/back/src/chunking/infrastructure/__init__.py`
- `app/back/src/chunking/infrastructure/schema2_source.py`
- `app/back/src/chunking/domain/models.py`
- `app/back/tests/chunking/integration/test_schema2_source.py`
- `app/back/tests/chunking/unit/test_domain_models.py`

## Concerns

- No known functional concern within Task 2. Task 3 remains responsible for
  turning this pre-structural bundle into `StructuralBlock` instances.
- The working tree already contained unrelated modified and untracked files;
  they were not altered by this task.

## Review Fixes

Applied the Task 2 review findings without changing parser, indexing, or other
non-Task-2 code.

- Marker resolution is now fail-closed: duplicate marker numbers or a marker
  page number absent from `pages.json` produce `PAGE_TRACE_UNRESOLVED` and do
  not fall back to a conflicting text alignment.
- The source loader rejects bundles where `metadata.page_count` differs from
  `pages.page_count`.
- Every derived sidecar path is resolved before access and rejected when its
  resolved target escapes the configured `docs_normalized` root, including via
  a symlink.
- Removed the unused `cast` import from `schema2_source.py`.

### Review TDD Evidence

Added three regression tests first:

1. A Markdown marker for pages absent from `pages.json` must abstain rather
   than create empty page traces.
2. Mismatched metadata/pages counts must be rejected.
3. A metadata-sidecar symlink escaping the normalized root must be rejected.

The RED run produced the first two expected failures. The symlink test was
collected but skipped because symlink creation is not permitted in this
Windows test session; it remains a regression test for environments where
symlinks are available.

### Review Verification

```powershell
$env:TMP=(Resolve-Path '.').Path + '\pytest-temp'; $env:TEMP=$env:TMP; New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null; .\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/integration/test_schema2_source.py -q --basetemp .\pytest-basetemp-task2-fix
```

Result: `8 passed, 1 skipped in 0.15s`.

## Final Review Fix

`SourceSpanResolver` now rejects duplicate `page_number` values in
`pages.json` before it attempts marker or text-alignment resolution. This
prevents a later page record from overwriting an earlier record in the page
lookup dictionary and returns `PAGE_TRACE_UNRESOLVED` instead.

### Final Review TDD Evidence

Added a regression test with one valid Markdown page marker and two
`pages.json` entries for page `1`. The RED run showed that the resolver used
the later page record. The resolver now detects duplicate source page numbers
at the beginning of `resolve` and abstains before constructing the lookup.

### Final Review Verification

```powershell
$env:TMP=(Resolve-Path '.').Path + '\pytest-temp'; $env:TEMP=$env:TMP; New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null; .\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/integration/test_schema2_source.py -q --basetemp .\pytest-basetemp-task2-fix2
```

Result: `9 passed, 1 skipped in 0.17s`.
```
