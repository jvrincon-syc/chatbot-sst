# Task 1 review package v2

## Files
app/back/src/chunking/__init__.py
app/back/src/chunking/domain/__init__.py
app/back/src/chunking/domain/enums.py
app/back/src/chunking/domain/errors.py
app/back/src/chunking/domain/invariants.py
app/back/src/chunking/domain/policies.py
app/back/src/chunking/domain/models.py
app/back/src/chunking/application/__init__.py
app/back/src/chunking/application/ports.py
app/back/tests/chunking/unit/test_domain_models.py
docs/chunking/chunking_policy.md
.superpowers/sdd/task-1-report.md

## FILE: app/back/src/chunking/__init__.py
```
"""Chunking bounded context."""
```

## FILE: app/back/src/chunking/domain/__init__.py
```
"""Domain contracts and policies for structural chunking."""
```

## FILE: app/back/src/chunking/domain/enums.py
```
from __future__ import annotations

from enum import StrEnum


class StructuralBlockKind(StrEnum):
    """Supported structural elements supplied by a normalized document."""

    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    FORM = "form"
    NOTE = "note"


class ZeroOverlapReason(StrEnum):
    """Auditable semantic reasons for intentionally omitting overlap."""

    DOCUMENT_START = "document_start"
    SECTION_BOUNDARY = "section_boundary"
    TABLE_OR_FORM_BOUNDARY = "table_or_form_boundary"
```

## FILE: app/back/src/chunking/domain/errors.py
```
from __future__ import annotations


class ChunkingError(ValueError):
    """Base error for invalid chunking domain data."""


class ChunkingProfileError(ChunkingError):
    """Raised when a chunking profile is internally inconsistent."""


class ChunkInvariantError(ChunkingError):
    """Raised when chunks cannot preserve their required provenance."""
```

## FILE: app/back/src/chunking/domain/invariants.py
```
from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from chunking.domain.errors import ChunkInvariantError, ChunkingProfileError


def require_non_empty(value: str, *, field_name: str) -> str:
    """Return a non-blank string or reject missing domain content."""
    if not value.strip():
        raise ChunkInvariantError(f"{field_name} must not be empty")
    return value


def require_non_negative(value: int, *, field_name: str) -> int:
    """Return a non-negative range endpoint or reject it."""
    if value < 0:
        raise ChunkInvariantError(f"{field_name} must be non-negative")
    return value


def require_positive(value: int, *, field_name: str) -> int:
    """Return a positive count or reject it."""
    if value <= 0:
        raise ChunkInvariantError(f"{field_name} must be positive")
    return value


def require_ordered(
    start: int,
    end: int,
    *,
    start_name: str,
    end_name: str,
) -> None:
    """Reject an inverted inclusive provenance range."""
    if end < start:
        raise ChunkInvariantError(f"{end_name} must be greater than or equal to {start_name}")


def require_unique(values: Iterable[str], *, field_name: str) -> None:
    """Reject repeated stable identifiers."""
    materialized = tuple(values)
    if len(materialized) != len(set(materialized)):
        raise ChunkInvariantError(f"{field_name} must be unique")


def require_enum_member(
    value: object,
    *,
    enum_type: type[Enum],
    field_name: str,
) -> None:
    """Reject values that are not members of the required runtime enum."""
    if not isinstance(value, enum_type):
        raise ChunkInvariantError(f"{field_name} must be a valid {enum_type.__name__}")


def require_profile_order(
    minimum: int,
    target: int,
    maximum: int,
) -> None:
    """Validate the child-size ordering required by a profile."""
    if not minimum <= target <= maximum:
        raise ChunkingProfileError(
            "child_min_tokens must be less than or equal to "
            "child_target_tokens and child_max_tokens"
        )


def require_overlap_bounds(minimum: int, maximum: int, child_maximum: int) -> None:
    """Validate overlap limits against the inclusive child token cap."""
    if minimum > maximum:
        raise ChunkingProfileError(
            "overlap_min_tokens must be less than or equal to overlap_max_tokens"
        )
    if maximum >= child_maximum:
        raise ChunkingProfileError(
            "overlap_max_tokens must be less than child_max_tokens"
        )
```

## FILE: app/back/src/chunking/domain/policies.py
```
from __future__ import annotations

from dataclasses import dataclass

from chunking.domain.enums import ZeroOverlapReason
from chunking.domain.errors import ChunkInvariantError


@dataclass(frozen=True)
class ZeroOverlapPolicy:
    """Defines the semantic boundaries where zero overlap is allowed."""

    allowed_reasons: frozenset[ZeroOverlapReason]

    def __post_init__(self) -> None:
        if any(not isinstance(reason, ZeroOverlapReason) for reason in self.allowed_reasons):
            raise ChunkInvariantError(
                "allowed_reasons must contain only valid ZeroOverlapReason values"
            )

    def allows(self, reason: ZeroOverlapReason | None) -> bool:
        """Return whether the policy explicitly permits the reason."""
        return reason is not None and reason in self.allowed_reasons


LOCAL_STRUCTURAL_ZERO_OVERLAP_POLICY = ZeroOverlapPolicy(
    allowed_reasons=frozenset(
        {
            ZeroOverlapReason.DOCUMENT_START,
            ZeroOverlapReason.TABLE_OR_FORM_BOUNDARY,
        }
    )
)
```

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
class NormalizedDocumentBundle:
    """Domain view of an approved normalized document for chunking."""

    document_id: str
    source_hash: str
    corpus_version: str
    blocks: tuple[StructuralBlock, ...]

    def __post_init__(self) -> None:
        require_non_empty(self.document_id, field_name="document_id")
        require_non_empty(self.source_hash, field_name="source_hash")
        require_non_empty(self.corpus_version, field_name="corpus_version")
        if not self.blocks:
            raise ChunkInvariantError("blocks must not be empty")
        require_unique((block.block_id for block in self.blocks), field_name="block_ids")
        if any(block.document_id != self.document_id for block in self.blocks):
            raise ChunkInvariantError("all blocks must belong to document_id")


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
        block_ids = {block.block_id for block in document.blocks}
        for parent in self.parents:
            if not set(parent.block_ids).issubset(block_ids):
                raise ChunkInvariantError(
                    "parent block_ids must exist in the normalized document blocks"
                )


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

## FILE: app/back/src/chunking/application/__init__.py
```
"""Application ports for structural chunking."""
```

## FILE: app/back/src/chunking/application/ports.py
```
from __future__ import annotations

from typing import Protocol

from chunking.domain.models import ChunkBundle, ChunkingProfile, NormalizedDocumentBundle


class TokenCounterPort(Protocol):
    """Counts canonical tokens without exposing a tokenizer implementation."""

    def count_tokens(self, text: str) -> int:
        """Return the canonical token count for non-empty chunk text."""


class StructuralChunkerPort(Protocol):
    """Builds validated structural chunks from a normalized document."""

    def chunk(
        self,
        document: NormalizedDocumentBundle,
        profile: ChunkingProfile,
    ) -> ChunkBundle:
        """Return the deterministic chunk bundle for one document and profile."""


class ChunkBundleRepositoryPort(Protocol):
    """Persists complete chunk outputs through an infrastructure adapter."""

    def replace(self, bundle: ChunkBundle) -> None:
        """Atomically replace chunks for the bundle document and profile."""
```

## FILE: app/back/tests/chunking/unit/test_domain_models.py
```
from __future__ import annotations

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
    block = StructuralBlock.create(
        document_id="doc-1",
        ordinal=0,
        kind=StructuralBlockKind.PARAGRAPH,
        text="Procedimiento seguro",
        source_span=_span(),
    )
    document = NormalizedDocumentBundle(
        document_id="doc-1",
        source_hash="source-hash",
        corpus_version="corpus-v1",
        blocks=(block,),
    )
    parent = ParentChunk.create(
        document_id="doc-1",
        profile_id="local-structural-v1",
        ordinal=0,
        text="Procedimiento seguro",
        source_span=_span(),
        block_ids=(block.block_id,),
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


def test_rechaza_parent_con_block_id_que_no_existe_en_documento_normalizado() -> None:
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

    with pytest.raises(ChunkInvariantError, match="block_ids"):
        ChunkingRun.create(document=document, bundle=bundle)


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


def test_rechaza_zero_overlap_reason_invalido_al_validar_bundle() -> None:
    child = _child(zero_overlap_reason="not-a-reason")

    with pytest.raises(ChunkInvariantError, match="zero_overlap_reason"):
        ChunkBundle(
            document_id="doc-1",
            profile=_profile(),
            parents=(_parent(),),
            children=(child,),
        )
```

## FILE: docs/chunking/chunking_policy.md
```
# Chunking Policy

## Canonical Profile

`local-structural-v1` is the local structural chunking profile. It uses a
canonical tokenizer selected in the [decision log](decision-log.md), though the
tokenizer implementation is deliberately outside this contract task.

| Setting | Value |
| --- | ---: |
| Child minimum tokens | 250 |
| Child target tokens | 350 |
| Child maximum tokens | 450 |
| Overlap ratio | 0.12 |
| Overlap minimum tokens | 30 |
| Overlap maximum tokens | 60 |

The target overlap is `round(350 * 0.12)`, or 42 tokens. It is clamped to the
configured overlap range. The child maximum includes overlap tokens; a child
whose complete canonical-token count exceeds 450 is invalid.

## Invariants

- `child_min_tokens <= child_target_tokens <= child_max_tokens`.
- `0 <= overlap_ratio <= 1`.
- `overlap_min_tokens <= overlap_max_tokens < child_max_tokens`.
- Each child references an existing parent in the same document and profile.
- Each parent block ID must reference a block in the normalized document before
  a chunking run is created.
- Source pages and character offsets are non-negative, ordered, and auditable.
- Structural blocks, parents, and children cannot have blank text.
- Structural block kinds and zero-overlap reasons are validated as runtime enum
  members; strings that merely resemble enum values are rejected.
- IDs are deterministic SHA-256 identities over content, profile, and stable
  structural position. Bundle and run fingerprints include canonical parent and
  child payloads, including child token count, overlap token count, and the
  zero-overlap reason.

## Zero Overlap

Zero overlap is fail-closed. It is permitted only when the child carries one of
the profile's explicit semantic exceptions:

- `document_start`
- `table_or_form_boundary`

`section_boundary` exists as an enum for a future profile, but is not allowed
by `local-structural-v1`. A nonzero overlap must stay within the configured
minimum and maximum range.

## Boundaries

These contracts contain no filesystem, FastAPI, parser, SDK, or tokenizer
implementation. Pydantic remains at external schema boundaries; the chunking
domain and application ports use immutable dataclasses and Python protocols.
```

## FILE: .superpowers/sdd/task-1-report.md
```
# Task 1 Report: Chunking Contracts, Profile, and Invariants

## Status

Completed without a commit. The task creates the chunking domain and
application contracts only; it does not change the active page-based parser or
add a tokenizer, filesystem, FastAPI, SDK, or provider integration.

## Delivered Contract

- Added immutable domain models for `NormalizedDocumentBundle`,
  `StructuralBlock`, `SourceSpan`, `ParentChunk`, `ChildChunk`, `ChunkBundle`,
  `ChunkingProfile`, and `ChunkingRun`.
- Added `local-structural-v1` with child sizes `250/350/450`, overlap ratio
  `0.12`, and overlap bounds `30/60`.
- Enforced profile coherence, non-empty content, valid source spans, existing
  child parents, profile-scoped overlap bounds, and the inclusive child token
  maximum.
- Zero overlap is fail-closed: `local-structural-v1` permits only
  `document_start` and `table_or_form_boundary`. `section_boundary` is defined
  for future profiles but is rejected by this profile.
- IDs, profile fingerprints, bundle fingerprints, and run IDs are SHA-256,
  deterministic, and bound to content, profile, and structural position.
- Added small `TokenCounterPort`, `StructuralChunkerPort`, and
  `ChunkBundleRepositoryPort` protocols with no infrastructure dependency.
- Documented the profile, invariants, zero-overlap policy, and boundaries.

## TDD Evidence

The test module was written before production code. The initial focused run
failed during collection with `ModuleNotFoundError: chunking.domain`, as
expected. Later RED cycles verified that direct construction could bypass
empty-content and deterministic-ID checks; the domain models were then updated
to enforce those invariants during construction.

## Verification

Focused command executed:

```powershell
$env:TMP=(Resolve-Path '.').Path + '\pytest-temp'; $env:TEMP=$env:TMP; New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null; .\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_domain_models.py -q --basetemp .\pytest-basetemp-task1
```

Result: `12 passed` in `0.03s`.

Additional checks:

- `python -m compileall -q app/back/src/chunking` passed.
- `git diff --check` produced no whitespace errors for this task's files.
- A targeted import scan found no Pydantic, FastAPI, filesystem, SDK, parser,
  tokenizer, or network dependency in the new chunking package.

## Concern

Pytest emitted one existing environmental warning because it cannot write to
the repository `.pytest_cache` (`WinError 5`). This did not affect collection
or execution: the focused suite passed using the requested workspace-local
temporary directory and base temp path.

## Review Fixes

Applied the Task 1 review findings without parser or integration changes.

- Bundle fingerprints now include complete canonical parent and child payloads.
  Child payloads include `token_count`, `overlap_tokens`, and
  `zero_overlap_reason`; run IDs also include the complete bundle payload.
- `ChunkBundle.validate_against_document()` validates every parent `block_id`
  against `NormalizedDocumentBundle.blocks`, and `ChunkingRun.create()` invokes
  it before creating run metadata.
- Structural block kinds, profile and policy zero-overlap reason sets, and
  bundle child zero-overlap reasons now receive explicit runtime enum checks.
- Added regression coverage for overlap-only fingerprint changes, unknown
  parent block IDs, and invalid enum values.

Focused review-fix verification executed:

```powershell
$env:TMP=(Resolve-Path '.').Path + '\pytest-temp'; $env:TEMP=$env:TMP; New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null; .\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_domain_models.py -q --basetemp .\pytest-basetemp-task1-fix
```

Result: `16 passed` in `0.07s`. The same existing `.pytest_cache` permission
warning was emitted and did not affect the focused suite.
```
