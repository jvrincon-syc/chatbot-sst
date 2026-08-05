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
