"""The legacy adapter must resolve the provider from the durable profile.

``document.profile`` is still accepted for compatibility, but it is now compared
field by field against the profile resolved from ``indexing_profiles`` and any
mismatch fails closed instead of embedding into a different vector space.
"""

from __future__ import annotations

import pytest

from indexing.domain.models import (
    IndexableDocument,
    IndexingProfile,
    NormalizedArtifactRefs,
)
from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.llama_index.pipeline_factory import (
    ProfileSemanticMismatchError,
    _durable_provider_profile,
)


DURABLE = ResolvedIndexingProfile(
    profile_id="local-bge-m3-v1",
    ingestion_origin="local",
    chunking_version="structure-aware-v1",
    embedding_provider="bge",
    embedding_model="BAAI/bge-m3",
    embedding_dimension=1024,
    distance_metric="cosine",
    vector_table="idx_vec_local_bge_m3_v1",
    metadata_schema_version="2.0",
    active=True,
    config_hash="a" * 64,
)


def _document(**profile_overrides: object) -> IndexableDocument:
    values: dict[str, object] = {
        "profile_id": DURABLE.profile_id,
        "chunking_version": DURABLE.chunking_version,
        "embedding_provider": DURABLE.embedding_provider,
        "embedding_model": DURABLE.embedding_model,
        "embedding_dimension": DURABLE.embedding_dimension,
        "vector_store": DURABLE.vector_table,
        "metadata_schema_version": DURABLE.metadata_schema_version,
    }
    values.update(profile_overrides)
    return IndexableDocument(
        document_id="doc_1",
        source_relpath="unit/example.md",
        source_hash="b" * 64,
        document_status="processed",
        artifacts=NormalizedArtifactRefs(
            markdown="unit/example.md",
            metadata="unit/example.metadata.json",
            pages="unit/example.pages.json",
            tables="unit/example.tables.json",
            forms="unit/example.forms.json",
        ),
        profile=IndexingProfile.model_validate(values),
    )


def test_usa_el_perfil_durable_cuando_la_peticion_coincide() -> None:
    provider_profile = _durable_provider_profile(
        document=_document(),
        resolved_profile=DURABLE,
    )

    assert provider_profile.embedding_provider == DURABLE.embedding_provider
    assert provider_profile.embedding_model == DURABLE.embedding_model
    assert provider_profile.embedding_dimension == DURABLE.embedding_dimension
    assert provider_profile.vector_store == DURABLE.vector_table


@pytest.mark.parametrize(
    "override",
    [
        {"embedding_provider": "voyage"},
        {"embedding_model": "voyage-4"},
        {"embedding_dimension": 512},
        {"chunking_version": "otra-version"},
        {"metadata_schema_version": "1.0"},
        {"profile_id": "otro-perfil"},
    ],
)
def test_falla_cerrado_cuando_la_peticion_difiere_del_perfil_durable(
    override: dict[str, object],
) -> None:
    with pytest.raises(ProfileSemanticMismatchError):
        _durable_provider_profile(
            document=_document(**override),
            resolved_profile=DURABLE,
        )
