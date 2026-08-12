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

    page_start: int | None
    page_end: int | None
    char_start: int
    char_end: int

    def __post_init__(self) -> None:
        if (self.page_start is None) != (self.page_end is None):
            raise ChunkInvariantError("page_start and page_end must both be null or both be present")
        if self.page_start is not None:
            require_positive(self.page_start, field_name="page_start")
            require_positive(self.page_end, field_name="page_end")
            require_ordered(
                self.page_start,
                self.page_end,
                start_name="page_start",
                end_name="page_end",
            )
        require_non_negative(self.char_start, field_name="char_start")
        require_non_negative(self.char_end, field_name="char_end")
        require_ordered(
            self.char_start,
            self.char_end,
            start_name="char_start",
            end_name="char_end",
        )

    def as_payload(self) -> dict[str, int | None]:
        """Return a deterministic representation for IDs and fingerprints."""
        return {
            "page_start": self.page_start,
            "page_end": self.page_end,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


@dataclass(frozen=True)
class OverlapSpan:
    """Exact token interval of a repeated overlap segment inside one child."""

    token_start: int
    token_end: int

    def __post_init__(self) -> None:
        require_non_negative(self.token_start, field_name="token_start")
        require_non_negative(self.token_end, field_name="token_end")
        if self.token_end <= self.token_start:
            raise ChunkInvariantError("token_end must be greater than token_start")

    def as_payload(self) -> dict[str, int]:
        """Return a deterministic representation for overlap metadata."""
        return {
            "token_start": self.token_start,
            "token_end": self.token_end,
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
class NormalizedDocumentPlatformContext:
    """Platform provenance carried with, but not defining, chunk identity."""

    project_id: str
    source_document_id: str
    source_document_revision_id: str
    processing_profile_id: str
    processing_profile_fingerprint: str
    normalized_document_id: str | None = None
    rag_variant_id: str | None = None
    semantic_recipe_fingerprint: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "project_id",
            "source_document_id",
            "source_document_revision_id",
            "processing_profile_id",
            "processing_profile_fingerprint",
        ):
            require_non_empty(getattr(self, field_name), field_name=field_name)
        if (self.rag_variant_id is None) != (self.semantic_recipe_fingerprint is None):
            raise ChunkInvariantError(
                "rag_variant_id and semantic_recipe_fingerprint must be set together"
            )


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
    structural_blocks: tuple[StructuralBlock, ...] = ()
    sidecars: ValidatedSidecars = field(default_factory=ValidatedSidecars)
    warnings: tuple[str, ...] = ()
    platform_context: NormalizedDocumentPlatformContext | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.document_id, field_name="document_id")
        require_non_empty(self.source_hash, field_name="source_hash")
        require_non_empty(self.corpus_version, field_name="corpus_version")
        require_non_empty(self.markdown, field_name="markdown")
        require_unique(
            (block.block_id for block in self.structural_blocks),
            field_name="structural_block_ids",
        )
        if any(block.document_id != self.document_id for block in self.structural_blocks):
            raise ChunkInvariantError(
                "all structural_blocks must belong to document_id"
            )


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
    token_start: int
    token_end: int
    token_count: int
    overlap_previous_tokens: int
    overlap_next_tokens: int
    overlap_previous_span: OverlapSpan | None = None
    overlap_next_span: OverlapSpan | None = None
    context_prefix: str = ""
    zero_overlap_reasons: frozenset[ZeroOverlapReason] = field(default_factory=frozenset)
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_non_empty(self.chunk_id, field_name="chunk_id")
        require_non_empty(self.document_id, field_name="document_id")
        require_non_empty(self.profile_id, field_name="profile_id")
        require_non_empty(self.parent_id, field_name="parent_id")
        require_non_negative(self.ordinal, field_name="ordinal")
        require_non_empty(self.text, field_name="text")
        require_non_negative(self.token_start, field_name="token_start")
        require_positive(self.token_end, field_name="token_end")
        if self.token_end <= self.token_start:
            raise ChunkInvariantError("token_end must be greater than token_start")
        require_positive(self.token_count, field_name="token_count")
        require_non_negative(
            self.overlap_previous_tokens,
            field_name="overlap_previous_tokens",
        )
        require_non_negative(
            self.overlap_next_tokens,
            field_name="overlap_next_tokens",
        )
        if self.overlap_previous_tokens >= self.token_count:
            raise ChunkInvariantError(
                "overlap_previous_tokens must be smaller than token_count"
            )
        if self.overlap_next_tokens >= self.token_count:
            raise ChunkInvariantError(
                "overlap_next_tokens must be smaller than token_count"
            )
        if any(
            not isinstance(reason, ZeroOverlapReason)
            for reason in self.zero_overlap_reasons
        ):
            raise ChunkInvariantError(
                "zero_overlap_reasons must contain only valid ZeroOverlapReason values"
            )
        self._validate_overlap_span(
            overlap_tokens=self.overlap_previous_tokens,
            overlap_span=self.overlap_previous_span,
            field_name="overlap_previous_span",
        )
        self._validate_overlap_span(
            overlap_tokens=self.overlap_next_tokens,
            overlap_span=self.overlap_next_span,
            field_name="overlap_next_span",
        )
        has_zero_boundary = (
            self.overlap_previous_tokens == 0 or self.overlap_next_tokens == 0
        )
        if has_zero_boundary and not self.zero_overlap_reasons:
            raise ChunkInvariantError(
                "zero_overlap_reasons are required when a child has a zero-overlap boundary"
            )
        if not has_zero_boundary and self.zero_overlap_reasons:
            raise ChunkInvariantError(
                "zero_overlap_reasons require at least one zero-overlap boundary"
            )
        expected_id = _stable_id(
            "child",
            {
                "document_id": self.document_id,
                "profile_id": self.profile_id,
                "parent_id": self.parent_id,
                "ordinal": self.ordinal,
                "context_prefix": self.context_prefix,
                "text": self.text,
                "source_span": self.source_span.as_payload(),
                "token_start": self.token_start,
                "token_end": self.token_end,
            },
        )
        if self.chunk_id != expected_id:
            raise ChunkInvariantError("chunk_id must match content and structural position")

    def _validate_overlap_span(
        self,
        *,
        overlap_tokens: int,
        overlap_span: OverlapSpan | None,
        field_name: str,
    ) -> None:
        if overlap_tokens == 0:
            if overlap_span is not None:
                raise ChunkInvariantError(
                    f"{field_name} must be null when its overlap token count is zero"
                )
            return
        if overlap_span is None:
            raise ChunkInvariantError(
                f"{field_name} is required when its overlap token count is positive"
            )
        if overlap_span.token_end - overlap_span.token_start != overlap_tokens:
            raise ChunkInvariantError(
                f"{field_name} must match its overlap token count exactly"
            )

    @property
    def chunk_index(self) -> int:
        """Return the stable ordering index within one parent."""
        return self.ordinal

    def as_payload(self) -> dict[str, object]:
        """Return the complete canonical child payload for traceability."""
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "profile_id": self.profile_id,
            "parent_id": self.parent_id,
            "ordinal": self.ordinal,
            "context_prefix": self.context_prefix,
            "text": self.text,
            "source_span": self.source_span.as_payload(),
            "token_start": self.token_start,
            "token_end": self.token_end,
            "token_count": self.token_count,
            "overlap_previous_tokens": self.overlap_previous_tokens,
            "overlap_next_tokens": self.overlap_next_tokens,
            "overlap_previous_span": (
                self.overlap_previous_span.as_payload()
                if self.overlap_previous_span is not None
                else None
            ),
            "overlap_next_span": (
                self.overlap_next_span.as_payload()
                if self.overlap_next_span is not None
                else None
            ),
            "zero_overlap_reasons": sorted(
                reason.value for reason in self.zero_overlap_reasons
            ),
            "warnings": list(self.warnings),
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
        token_start: int,
        token_end: int,
        token_count: int,
        overlap_previous_tokens: int,
        overlap_next_tokens: int,
        overlap_previous_span: OverlapSpan | None = None,
        overlap_next_span: OverlapSpan | None = None,
        context_prefix: str = "",
        zero_overlap_reasons: frozenset[ZeroOverlapReason] = frozenset(),
        warnings: tuple[str, ...] = (),
    ) -> ChildChunk:
        """Create a child with a deterministic parent-scoped identifier."""
        require_non_empty(document_id, field_name="document_id")
        require_non_empty(profile_id, field_name="profile_id")
        require_non_empty(parent_id, field_name="parent_id")
        require_non_negative(ordinal, field_name="ordinal")
        require_non_empty(text, field_name="text")
        require_non_negative(token_start, field_name="token_start")
        require_positive(token_end, field_name="token_end")
        if token_end <= token_start:
            raise ChunkInvariantError("token_end must be greater than token_start")
        require_positive(token_count, field_name="token_count")
        require_non_negative(
            overlap_previous_tokens,
            field_name="overlap_previous_tokens",
        )
        require_non_negative(
            overlap_next_tokens,
            field_name="overlap_next_tokens",
        )
        if overlap_previous_tokens >= token_count:
            raise ChunkInvariantError(
                "overlap_previous_tokens must be smaller than token_count"
            )
        if overlap_next_tokens >= token_count:
            raise ChunkInvariantError(
                "overlap_next_tokens must be smaller than token_count"
            )
        if any(
            not isinstance(reason, ZeroOverlapReason)
            for reason in zero_overlap_reasons
        ):
            raise ChunkInvariantError(
                "zero_overlap_reasons must contain only valid ZeroOverlapReason values"
            )
        chunk_id = _stable_id(
            "child",
            {
                "document_id": document_id,
                "profile_id": profile_id,
                "parent_id": parent_id,
                "ordinal": ordinal,
                "context_prefix": context_prefix,
                "text": text,
                "source_span": source_span.as_payload(),
                "token_start": token_start,
                "token_end": token_end,
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
            token_start,
            token_end,
            token_count,
            overlap_previous_tokens,
            overlap_next_tokens,
            overlap_previous_span,
            overlap_next_span,
            context_prefix,
            zero_overlap_reasons,
            warnings,
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
            if child.token_count > self.profile.child_max_tokens:
                raise ChunkInvariantError(
                    "child token_count must not exceed child_max_tokens including overlap"
                )
            for overlap_tokens in (
                child.overlap_previous_tokens,
                child.overlap_next_tokens,
            ):
                if overlap_tokens > 0 and not (
                    self.profile.overlap_min_tokens
                    <= overlap_tokens
                    <= self.profile.overlap_max_tokens
                ):
                    raise ChunkInvariantError(
                        "overlap token counts must be within profile bounds"
                    )
            if not child.zero_overlap_reasons.issubset(
                self.profile.zero_overlap_policy.allowed_reasons
            ):
                raise ChunkInvariantError(
                    "zero_overlap_reasons are not allowed by the profile policy"
                )

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
        available_block_ids = {block.block_id for block in document.structural_blocks}
        if not available_block_ids:
            raise ChunkInvariantError(
                "document structural_blocks are required to validate parent block_ids"
            )
        for parent in self.parents:
            missing = [block_id for block_id in parent.block_ids if block_id not in available_block_ids]
            if missing:
                raise ChunkInvariantError("parent block_ids must exist in document structural_blocks")


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
