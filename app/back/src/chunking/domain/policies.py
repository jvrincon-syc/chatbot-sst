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
            ZeroOverlapReason.SECTION_BOUNDARY,
            ZeroOverlapReason.TABLE_OR_FORM_BOUNDARY,
        }
    )
)
