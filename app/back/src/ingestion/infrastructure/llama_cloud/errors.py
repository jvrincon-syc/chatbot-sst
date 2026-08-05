from __future__ import annotations

from ingestion.application.ports.provider_errors import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderJobFailedError,
    ProviderMalformedResultError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnsupportedFeatureError,
)

__all__ = [
    "ProviderAuthenticationError",
    "ProviderError",
    "ProviderJobFailedError",
    "ProviderMalformedResultError",
    "ProviderQuotaError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "ProviderUnsupportedFeatureError",
]
