from __future__ import annotations


class ChunkingError(ValueError):
    """Base error for invalid chunking domain data."""


class ChunkingProfileError(ChunkingError):
    """Raised when a chunking profile is internally inconsistent."""


class ChunkInvariantError(ChunkingError):
    """Raised when chunks cannot preserve their required provenance."""
