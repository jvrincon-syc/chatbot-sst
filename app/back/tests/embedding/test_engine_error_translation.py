"""The provider engine adapter must never leak a raw provider exception."""

from __future__ import annotations

import pytest

from embedding.application.engine_registry import (
    ProviderEngineAdapter,
    translate_engine_error,
)
from embedding.domain.errors import EmbeddingEngineUnavailable
from indexing.application.embedding_provider import (
    EmbeddingProviderAuthenticationError,
    EmbeddingProviderRateLimitError,
    EmbeddingProviderTimeoutError,
)

from pipeline_fixtures import build_profile


class _ExplodingProvider:
    """Stand-in provider whose calls raise a raw, secret-bearing exception."""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.model_name = "deterministic"

    @property
    def dimension(self) -> int:
        return 8

    def embed_documents(self, _texts):
        raise self._error

    def embed_queries(self, _texts):
        raise self._error


def _adapter(error: Exception) -> ProviderEngineAdapter:
    return ProviderEngineAdapter(
        profile=build_profile(),
        provider=_ExplodingProvider(error),
        normalization_applied="none",
        revision_reader=lambda _provider: "deterministic-v1",
    )


def test_embed_documents_traduce_el_error_crudo_del_proveedor() -> None:
    raw = EmbeddingProviderTimeoutError(
        "POST https://api.voyageai.com/v1/embeddings timed out; key sk-secret"
    )
    adapter = _adapter(raw)

    with pytest.raises(EmbeddingEngineUnavailable) as excinfo:
        adapter.embed_documents(["text"])

    message = str(excinfo.value)
    assert "voyageai.com" not in message
    assert "sk-secret" not in message
    assert excinfo.value.code == "EMBEDDING_ENGINE_UNAVAILABLE"
    assert getattr(excinfo.value, "reason") == "temporary_failure"
    # The original class is preserved as the cause, never in the public message.
    assert isinstance(excinfo.value.__cause__, EmbeddingProviderTimeoutError)


def test_embed_queries_traduce_el_error_crudo_del_proveedor() -> None:
    adapter = _adapter(EmbeddingProviderRateLimitError("rate limited: body {...}"))

    with pytest.raises(EmbeddingEngineUnavailable) as excinfo:
        adapter.embed_queries(["q"])

    assert "body" not in str(excinfo.value)
    assert getattr(excinfo.value, "reason") == "temporary_failure"


def test_translate_engine_error_distingue_familias() -> None:
    auth = translate_engine_error(
        EmbeddingProviderAuthenticationError("missing VOYAGE_API_KEY=xyz")
    )
    timeout = translate_engine_error(EmbeddingProviderTimeoutError("slow"))

    assert getattr(auth, "reason") == "authentication_failed"
    assert "xyz" not in str(auth)
    assert getattr(timeout, "reason") == "temporary_failure"
