"""Domain errors for retrieval, each carrying its public code."""

from __future__ import annotations


class RetrievalDomainError(Exception):
    """Base class for retrieval domain errors with a stable public code."""

    code = "RETRIEVAL_DOMAIN_ERROR"
    http_status = 400


class RetrievalProfileNotFound(RetrievalDomainError):
    """The retrieval profile does not exist."""

    code = "RETRIEVAL_PROFILE_NOT_FOUND"
    http_status = 404


class RetrievalProfileBlocked(RetrievalDomainError):
    """The retrieval profile exists but must not serve traffic."""

    code = "RETRIEVAL_PROFILE_BLOCKED"
    http_status = 409


class LexicalFallbackNotAllowed(RetrievalDomainError):
    """Vector retrieval is blocked and the profile forbids lexical-only answers."""

    code = "RETRIEVAL_PROFILE_BLOCKED"
    http_status = 409
