"""Registry that binds one durable embedding profile to exactly one engine.

The registry never picks "the first available provider". It resolves the engine
named by the durable profile and fails closed when that engine is missing,
unavailable or semantically different. There is no vector fallback: an
unavailable BGE runtime never becomes a Voyage runtime.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import os
from typing import Callable

from embedding.domain.errors import (
    EmbeddingEngineNotFound,
    EmbeddingEngineUnavailable,
    QueryEmbeddingUnsupported,
)
from embedding.domain.models import (
    UNKNOWN_REVISION,
    CompatibilityMismatch,
    CompatibilityReport,
    EmbeddingProfile,
    EmbeddingRuntimeMode,
    EmbeddingRuntimeStatus,
    Normalization,
)
from embedding.application.ports import EmbeddingEngine
from indexing.application.embedding_provider import (
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingProviderAuthenticationError,
    EmbeddingProviderConfigurationError,
    EmbeddingProviderRateLimitError,
    EmbeddingProviderResponseError,
    EmbeddingProviderTimeoutError,
)
from indexing.domain.models import IndexingProfile
from indexing.infrastructure.embeddings.bge import (
    BgeEmbeddingProvider,
    EmbeddingProviderUnavailableError,
)
from indexing.infrastructure.embeddings.factory import DeterministicEmbeddingProvider
from indexing.infrastructure.embeddings.settings import EmbeddingSettings
from indexing.infrastructure.embeddings.voyage import VoyageEmbeddingProvider


#: Normalization each runtime actually applies to its dense vectors.
_PROVIDER_NORMALIZATION: dict[str, Normalization] = {
    "bge": "l2",
    "voyage": "provider_normalized",
    "mock": "none",
}

#: Runtime mode recorded on every run started with this provider.
_PROVIDER_RUNTIME_MODE: dict[str, EmbeddingRuntimeMode] = {
    "bge": "local",
    "voyage": "cloud",
    "mock": "dry_run",
}

#: Revision the deterministic mock engine can honestly prove about itself.
_MOCK_REVISION = "deterministic-v1"

#: Providers kept for internal compatibility but never operational.
_STUB_PROVIDERS = frozenset({"cohere"})


def indexing_profile_from(profile: EmbeddingProfile) -> IndexingProfile:
    """Adapt a durable embedding profile to the legacy provider constructor."""

    return IndexingProfile(
        profile_id=profile.profile_id,
        chunking_version=profile.chunking_version,
        embedding_provider=profile.provider,
        embedding_model=profile.model,
        embedding_dimension=profile.dimension,
        vector_store=profile.vector_table,
        metadata_schema_version=profile.metadata_schema_version,
    )


def operational_settings(
    profile: EmbeddingProfile,
    environ: Mapping[str, str] | None = None,
) -> EmbeddingSettings:
    """Load operational settings from the environment, semantics from the profile.

    Credentials, timeouts, retries, batch size, device and cache come from the
    environment. Provider, model, dimension and distance metric are forced back
    to the durable profile so no environment variable can move a vector space.
    """

    base = EmbeddingSettings.from_env(os.environ if environ is None else environ)
    return base.model_copy(
        update={
            "provider": profile.provider,
            "model": profile.model,
            "dimension": profile.dimension,
            "distance_metric": profile.distance_metric,
        }
    )


@dataclass
class ProviderEngineAdapter:
    """Adapt an existing indexing embedding provider to the engine port.

    Every provider call is funnelled through :func:`translate_engine_error` so a
    raw SDK/provider exception (which can echo URLs, response bodies, Hugging
    Face cache paths or credentials) never crosses the application boundary.
    """

    profile: EmbeddingProfile
    provider: EmbeddingProvider
    normalization_applied: Normalization
    revision_reader: Callable[[EmbeddingProvider], str]

    @property
    def provider_name(self) -> str:
        """Return the provider name the engine implements."""

        return self.profile.provider

    @property
    def model_name(self) -> str:
        """Return the model the engine loaded."""

        return self.profile.model

    @property
    def dimension(self) -> int:
        """Return the dense vector dimension produced by the engine."""

        return int(self.provider.dimension)

    @property
    def normalization(self) -> Normalization:
        """Return the normalization the engine applies to its vectors."""

        return self.normalization_applied

    @property
    def supports_queries(self) -> bool:
        """Return whether the engine can embed queries."""

        return True

    def observe_revision(self) -> str:
        """Return the runtime-observable revision, or ``unknown_revision``."""

        return self.revision_reader(self.provider)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one document vector per input text."""

        try:
            return self.provider.embed_documents(list(texts)).vectors
        except EmbeddingError as error:
            raise translate_engine_error(error) from error

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one query vector per input text."""

        try:
            return self.provider.embed_queries(list(texts)).vectors
        except EmbeddingError as error:
            raise translate_engine_error(error) from error


def _bge_revision(provider: EmbeddingProvider) -> str:
    """Read the resolved Hugging Face commit of a BGE runtime.

    FlagEmbedding exposes no stable revision accessor, so two sources are tried,
    both of them runtime observations rather than operator claims:

    1. the config of an already loaded model, when the runtime exposes one;
    2. ``AutoConfig`` for the model named by the profile, which resolves the
       snapshot commit from the local Hugging Face cache without loading any
       weights.

    Anything that cannot actually be observed stays ``unknown_revision`` and
    therefore blocks verification.
    """

    model = getattr(provider, "_model", None)
    for attribute_path in (
        ("model", "config", "_commit_hash"),
        ("config", "_commit_hash"),
        ("model_revision",),
    ):
        current: object | None = model
        for attribute in attribute_path:
            current = getattr(current, attribute, None) if current is not None else None
        if isinstance(current, str) and current:
            return current
    return _hub_snapshot_revision(provider.model_name)


def _hub_snapshot_revision(model_name: str) -> str:
    """Resolve the cached Hugging Face snapshot commit for one model name."""

    try:
        from transformers import AutoConfig
    except ImportError:
        return UNKNOWN_REVISION
    try:
        config = AutoConfig.from_pretrained(model_name)
    except (OSError, ValueError):
        return UNKNOWN_REVISION
    commit = getattr(config, "_commit_hash", None)
    return commit if isinstance(commit, str) and commit else UNKNOWN_REVISION


def _voyage_revision(_provider: EmbeddingProvider) -> str:
    """Return ``unknown_revision``: the Voyage API exposes no model revision."""

    return UNKNOWN_REVISION


def _mock_revision(_provider: EmbeddingProvider) -> str:
    """Return the deterministic mock revision."""

    return _MOCK_REVISION


@dataclass
class DefaultEmbeddingEngineRegistry:
    """Resolve engines by exact durable profile, with no provider fallback."""

    environ: Mapping[str, str] | None = None
    allow_mock: bool = False
    _cache: dict[str, EmbeddingEngine] = field(default_factory=dict, init=False)

    def resolve_document_engine(self, profile: EmbeddingProfile) -> EmbeddingEngine:
        """Return the engine allowed to embed documents for this profile."""

        return self._resolve(profile)

    def resolve_query_engine(self, profile: EmbeddingProfile) -> EmbeddingEngine:
        """Return the engine allowed to embed queries for this profile."""

        engine = self._resolve(profile)
        if not engine.supports_queries:
            raise QueryEmbeddingUnsupported(
                f"engine for provider {profile.provider} cannot embed queries"
            )
        return engine

    def get_runtime_status(self, profile: EmbeddingProfile) -> EmbeddingRuntimeStatus:
        """Return operational availability without raising."""

        runtime_mode = _PROVIDER_RUNTIME_MODE.get(profile.provider, "legacy")
        try:
            engine = self._resolve(profile)
        except (EmbeddingEngineNotFound, EmbeddingEngineUnavailable) as error:
            return EmbeddingRuntimeStatus(
                profile_id=profile.profile_id,
                provider=profile.provider,
                model=profile.model,
                runtime_mode=runtime_mode,
                engine_available=False,
                supports_documents=False,
                supports_queries=False,
                blocked_reason=error.code,
            )
        return EmbeddingRuntimeStatus(
            profile_id=profile.profile_id,
            provider=profile.provider,
            model=profile.model,
            runtime_mode=runtime_mode,
            engine_available=True,
            engine_revision_observed=engine.observe_revision(),
            supports_documents=profile.can_embed_documents,
            supports_queries=profile.can_embed_queries and engine.supports_queries,
            blocked_reason=(
                None
                if profile.compatibility_gate_open
                else "EMBEDDING_PROFILE_COMPATIBILITY_NOT_PROVEN"
            ),
        )

    def validate_engine_compatibility(
        self,
        profile: EmbeddingProfile,
        engine: EmbeddingEngine,
    ) -> CompatibilityReport:
        """Compare every semantic field of the profile against the engine."""

        mismatches: list[CompatibilityMismatch] = []
        for field_name, expected, observed in (
            ("provider", profile.provider, engine.provider_name),
            ("model", profile.model, engine.model_name),
            ("dimension", str(profile.dimension), str(engine.dimension)),
            ("normalization", profile.normalization, engine.normalization),
        ):
            matches = (
                profile.normalization_matches_runtime(engine.normalization)
                if field_name == "normalization"
                else expected == observed
            )
            if not matches:
                mismatches.append(
                    CompatibilityMismatch(
                        field_name=field_name,
                        expected=str(expected),
                        observed=str(observed),
                    )
                )
        return CompatibilityReport(
            profile_id=profile.profile_id,
            compatible=not mismatches,
            mismatches=mismatches,
            revision_source="engine_observed",
        )

    def _resolve(self, profile: EmbeddingProfile) -> EmbeddingEngine:
        cached = self._cache.get(profile.profile_id)
        if cached is not None:
            return cached

        provider_name = profile.provider
        if provider_name in _STUB_PROVIDERS:
            raise EmbeddingEngineUnavailable(
                f"embedding provider {provider_name} has no operational runtime"
            )
        if provider_name == "mock" and not self.allow_mock:
            raise EmbeddingEngineUnavailable(
                "the deterministic mock engine is restricted to tests and dry-run"
            )
        if provider_name not in _PROVIDER_NORMALIZATION:
            raise EmbeddingEngineNotFound(
                f"no embedding engine is registered for provider {provider_name}"
            )

        settings = operational_settings(profile, self.environ)
        legacy_profile = indexing_profile_from(profile)
        try:
            engine = self._build_engine(
                profile=profile,
                legacy_profile=legacy_profile,
                settings=settings,
            )
        except (
            EmbeddingProviderConfigurationError,
            EmbeddingProviderAuthenticationError,
            EmbeddingProviderUnavailableError,
        ) as error:
            raise EmbeddingEngineUnavailable(
                f"embedding runtime for provider {provider_name} is not usable"
            ) from error
        self._cache[profile.profile_id] = engine
        return engine

    def _build_engine(
        self,
        *,
        profile: EmbeddingProfile,
        legacy_profile: IndexingProfile,
        settings: EmbeddingSettings,
    ) -> EmbeddingEngine:
        if profile.provider == "bge":
            provider: EmbeddingProvider = BgeEmbeddingProvider(
                profile=legacy_profile,
                settings=settings,
            )
            revision_reader = _bge_revision
        elif profile.provider == "voyage":
            provider = VoyageEmbeddingProvider(profile=legacy_profile, settings=settings)
            revision_reader = _voyage_revision
        else:
            provider = DeterministicEmbeddingProvider(
                profile=legacy_profile,
                settings=settings,
            )
            revision_reader = _mock_revision
        return ProviderEngineAdapter(
            profile=profile,
            provider=provider,
            normalization_applied=_PROVIDER_NORMALIZATION[profile.provider],
            revision_reader=revision_reader,
        )


#: Sanitized reason kinds, so callers can distinguish failure families without
#: ever seeing the provider's raw message. Every family still surfaces as
#: ``EMBEDDING_ENGINE_UNAVAILABLE`` at the HTTP boundary.
_ENGINE_ERROR_REASONS: tuple[tuple[type[EmbeddingError], str], ...] = (
    # Order matters: authentication is a subclass of configuration, so it must
    # be matched first.
    (EmbeddingProviderAuthenticationError, "authentication_failed"),
    (EmbeddingProviderConfigurationError, "missing_dependency_or_configuration"),
    (EmbeddingProviderUnavailableError, "runtime_unavailable"),
    (EmbeddingProviderTimeoutError, "temporary_failure"),
    (EmbeddingProviderRateLimitError, "temporary_failure"),
    (EmbeddingProviderResponseError, "provider_response_error"),
)


def _engine_error_reason(error: EmbeddingError) -> str:
    for error_type, reason in _ENGINE_ERROR_REASONS:
        if isinstance(error, error_type):
            return reason
    return "runtime_error"


def translate_engine_error(error: EmbeddingError) -> EmbeddingEngineUnavailable:
    """Translate a provider runtime failure into a sanitized domain error.

    Provider messages can echo credentials, URLs, response bodies or local
    Hugging Face cache paths, so nothing but a stable reason kind and the error
    class name crosses the boundary. The originating class is preserved as the
    exception cause for internal correlation, never in the public message.
    """

    reason = _engine_error_reason(error)
    domain_error = EmbeddingEngineUnavailable(
        f"embedding runtime failed ({reason})"
    )
    domain_error.reason = reason  # type: ignore[attr-defined]
    domain_error.origin_error_type = type(error).__name__  # type: ignore[attr-defined]
    return domain_error
