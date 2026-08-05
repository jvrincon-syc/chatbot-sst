from __future__ import annotations

from pathlib import Path

import pytest

from indexing.application.embedding_provider import (
    EmbeddingDimensionError,
    EmbeddingInputError,
    EmbeddingProviderAuthenticationError,
    EmbeddingProviderRateLimitError,
    EmbeddingProviderTimeoutError,
)
from indexing.domain.models import IndexingProfile
from indexing.infrastructure.embeddings.bge import BgeEmbeddingProvider
from indexing.infrastructure.embeddings.settings import EmbeddingSettings
from indexing.infrastructure.embeddings.voyage import VoyageEmbeddingProvider


class FakeRateLimitError(Exception):
    pass


def _profile(
    *,
    provider: str,
    model: str,
    dimension: int = 3,
) -> IndexingProfile:
    return IndexingProfile(
        profile_id=f"{provider}-profile",
        chunking_version="structure-aware-v1",
        embedding_provider=provider,
        embedding_model=model,
        embedding_dimension=dimension,
        vector_store="memory",
        metadata_schema_version="2.0",
    )


def test_bge_uses_corpus_and_query_methods_without_reloading_model() -> None:
    fake_model = FakeBgeModel()
    provider = BgeEmbeddingProvider(
        profile=_profile(provider="bge", model="BAAI/bge-m3"),
        settings=EmbeddingSettings(provider="bge", batch_size=2),
        model_loader=lambda _settings: fake_model,
    )

    document_batch = provider.embed_documents(["doc uno", "doc dos"])
    query_batch = provider.embed_queries(["consulta"])
    provider.embed_documents(["doc tres"])

    assert fake_model.corpus_calls == [(["doc uno", "doc dos"], 2), (["doc tres"], 2)]
    assert fake_model.query_calls == [(["consulta"], 2)]
    assert fake_model.load_count == 1
    assert document_batch.provider == "bge"
    assert query_batch.model == "BAAI/bge-m3"
    assert provider.capabilities.supports_sparse is True
    assert provider.capabilities.supports_multimodal is False


def test_bge_rejects_empty_texts_and_dimension_mismatch() -> None:
    provider = BgeEmbeddingProvider(
        profile=_profile(provider="bge", model="BAAI/bge-m3", dimension=4),
        settings=EmbeddingSettings(provider="bge"),
        model_loader=lambda _settings: FakeBgeModel(),
    )

    with pytest.raises(EmbeddingInputError):
        provider.embed_documents([""])
    with pytest.raises(EmbeddingDimensionError):
        provider.embed_queries(["consulta"])


def test_voyage_sets_document_and_query_input_type_and_reuses_client() -> None:
    client = FakeVoyageClient()
    provider = VoyageEmbeddingProvider(
        profile=_profile(provider="voyage", model="voyage-4"),
        settings=EmbeddingSettings(
            provider="voyage",
            voyage_api_key="secret-value",
            batch_size=2,
            timeout_seconds=12,
        ),
        client_factory=lambda _settings: client,
    )

    document_batch = provider.embed_documents(["doc uno", "doc dos"])
    query_batch = provider.embed_queries(["consulta"])

    assert client.calls == [
        {
            "texts": ["doc uno", "doc dos"],
            "model": "voyage-4",
            "input_type": "document",
            "output_dimension": 3,
        },
        {
            "texts": ["consulta"],
            "model": "voyage-4",
            "input_type": "query",
            "output_dimension": 3,
        },
    ]
    assert client.load_count == 1
    assert document_batch.normalized is True
    assert query_batch.provider == "voyage"


def test_voyage_requires_api_key_only_when_selected() -> None:
    bge_settings = EmbeddingSettings.from_env({"EMBEDDING_PROVIDER": "bge"})

    assert bge_settings.provider == "bge"

    with pytest.raises(EmbeddingProviderAuthenticationError):
        VoyageEmbeddingProvider(
            profile=_profile(provider="voyage", model="voyage-4"),
            settings=EmbeddingSettings(provider="voyage"),
            client_factory=lambda _settings: FakeVoyageClient(),
        ).embed_documents(["doc"])


def test_embedding_settings_use_hf_token_as_only_hugging_face_secret_name() -> None:
    settings = EmbeddingSettings.from_env(
        {
            "EMBEDDING_PROVIDER": "bge",
            "HUGGING_FACE_HUB_TOKEN": "legacy-token",
        }
    )

    assert settings.hf_token is None


def test_secrets_example_exposes_only_canonical_embedding_runtime_keys() -> None:
    repo_root = Path(__file__).parents[5]
    keys = _env_keys(repo_root / "secrets.example.env")

    assert "HF_TOKEN" in keys
    assert "HUGGING_FACE_HUB_TOKEN" not in keys
    assert "BGE_MODEL_NAME" not in keys
    assert "BGE_BATCH_SIZE" not in keys
    assert "BGE_PASSAGE_MAX_LENGTH" not in keys


@pytest.mark.parametrize(
    ("external_error", "expected_error"),
    [
        (TimeoutError("timeout"), EmbeddingProviderTimeoutError),
        (FakeRateLimitError("rate limit"), EmbeddingProviderRateLimitError),
    ],
)
def test_voyage_translates_external_errors(
    external_error: Exception,
    expected_error: type[Exception],
) -> None:
    provider = VoyageEmbeddingProvider(
        profile=_profile(provider="voyage", model="voyage-4"),
        settings=EmbeddingSettings(provider="voyage", voyage_api_key="secret-value"),
        client_factory=lambda _settings: FailingVoyageClient(external_error),
    )

    with pytest.raises(expected_error) as exc_info:
        provider.embed_queries(["consulta"])

    assert "secret-value" not in str(exc_info.value)


class FakeBgeModel:
    def __init__(self) -> None:
        self.load_count = 1
        self.corpus_calls: list[tuple[list[str], int]] = []
        self.query_calls: list[tuple[list[str], int]] = []

    def encode_corpus(self, texts, *, batch_size, max_length, **kwargs):
        self.corpus_calls.append((list(texts), batch_size))
        return {"dense_vecs": [[1.0, 0.0, 0.0] for _ in texts]}

    def encode_queries(self, texts, *, batch_size, max_length, **kwargs):
        self.query_calls.append((list(texts), batch_size))
        return {"dense_vecs": [[0.0, 1.0, 0.0] for _ in texts]}


class FakeVoyageResult:
    def __init__(self, embeddings: list[list[float]]) -> None:
        self.embeddings = embeddings


class FakeVoyageClient:
    def __init__(self) -> None:
        self.load_count = 1
        self.calls: list[dict[str, object]] = []

    def embed(
        self,
        texts,
        *,
        model: str,
        input_type: str,
        output_dimension: int,
        **kwargs,
    ) -> FakeVoyageResult:
        self.calls.append(
            {
                "texts": list(texts),
                "model": model,
                "input_type": input_type,
                "output_dimension": output_dimension,
            }
        )
        return FakeVoyageResult([[0.1, 0.2, 0.3] for _ in texts])


class FailingVoyageClient:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def embed(self, *args, **kwargs):
        raise self._error


def _env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys
