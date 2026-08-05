from __future__ import annotations


class ProviderError(Exception):
    """Base error for external provider failures."""


class ProviderAuthenticationError(ProviderError):
    """Authentication failed or credentials are missing."""


class ProviderQuotaError(ProviderError):
    """Provider quota or credit budget is exhausted."""


class ProviderRateLimitError(ProviderError):
    """Provider rate limit was reached."""


class ProviderTimeoutError(TimeoutError, ProviderError):
    """Provider request timed out."""


class ProviderJobFailedError(ProviderError):
    """Provider job finished in a failed state."""


class ProviderMalformedResultError(ProviderError):
    """Provider response did not match the expected contract."""


class ProviderUnsupportedFeatureError(ProviderError):
    """Requested provider feature is not supported by this adapter."""
