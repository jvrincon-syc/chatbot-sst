"""Domain errors for the bundle-first embedding pipeline.

Every error carries the public ``code`` published by the HTTP error envelope so
that the API layer never has to re-derive a taxonomy from exception classes.
"""

from __future__ import annotations


class EmbeddingDomainError(Exception):
    """Base class for embedding domain errors with a stable public code."""

    code = "EMBEDDING_DOMAIN_ERROR"
    http_status = 400


class EmbeddingProfileNotFound(EmbeddingDomainError):
    """The durable embedding profile does not exist."""

    code = "EMBEDDING_PROFILE_NOT_FOUND"
    http_status = 404


class EmbeddingProfileCompatibilityNotProven(EmbeddingDomainError):
    """The profile exists but was never verified against a real engine."""

    code = "EMBEDDING_PROFILE_COMPATIBILITY_NOT_PROVEN"
    http_status = 409


class EmbeddingEngineNotFound(EmbeddingDomainError):
    """No engine is registered for the provider named by the profile."""

    code = "EMBEDDING_ENGINE_NOT_FOUND"
    http_status = 409


class EmbeddingEngineUnavailable(EmbeddingDomainError):
    """The engine exists but its runtime cannot be used right now."""

    code = "EMBEDDING_ENGINE_UNAVAILABLE"
    http_status = 503


class EmbeddingEngineRevisionMismatch(EmbeddingDomainError):
    """The observed engine revision does not prove the profile revision."""

    code = "EMBEDDING_ENGINE_REVISION_MISMATCH"
    http_status = 409


class EmbeddingEngineSemanticMismatch(EmbeddingDomainError):
    """Provider, model, dimension, normalization, metric or fingerprint differ."""

    code = "EMBEDDING_ENGINE_SEMANTIC_MISMATCH"
    http_status = 409


class QueryEmbeddingUnsupported(EmbeddingDomainError):
    """The resolved engine cannot embed queries for this profile."""

    code = "QUERY_EMBEDDING_UNSUPPORTED"
    http_status = 409


class EmbeddingBundleInvalid(EmbeddingDomainError):
    """The embedding bundle failed validation and must not be indexed."""

    code = "EMBEDDING_BUNDLE_INVALID"
    http_status = 409


class EmbeddingBundleStale(EmbeddingDomainError):
    """The embedding bundle no longer matches its source chunk bundle."""

    code = "EMBEDDING_BUNDLE_STALE"
    http_status = 409


class EmbeddingBundleNotFound(EmbeddingDomainError):
    """The embedding bundle does not exist."""

    code = "EMBEDDING_BUNDLE_NOT_FOUND"
    http_status = 404


class ChunkBundleNotFound(EmbeddingDomainError):
    """The source chunk bundle is not registered in the durable ledger."""

    code = "CHUNK_BUNDLE_NOT_FOUND"
    http_status = 404


class EmbeddingRunNotFound(EmbeddingDomainError):
    """The embedding run does not exist."""

    code = "EMBEDDING_RUN_NOT_FOUND"
    http_status = 404


class IdempotencyConflict(EmbeddingDomainError):
    """One idempotency key was reused for a different request fingerprint."""

    code = "IDEMPOTENCY_CONFLICT"
    http_status = 409


class EmbeddingExecutorBusy(EmbeddingDomainError):
    """The bounded embedding queue is saturated."""

    code = "EMBEDDING_EXECUTOR_BUSY"
    http_status = 429
