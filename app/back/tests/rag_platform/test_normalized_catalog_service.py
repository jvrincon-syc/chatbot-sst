"""Task 5: persistencia del catálogo ``normalized`` enriquecido por proyecto.

``PersistNormalizedArtifactCatalogUseCase`` compone piezas existentes: resuelve
el normalizado por identidad exacta (``ResolveNormalizedArtifactUseCase``), lee
la receta de procesamiento (proveedor/motor/origen) y, si el normalizado nació
en contexto de variante, adjunta la provenance semántica (variante + receta).

La identidad física sigue siendo ``project + revisión + fingerprint de
procesamiento``; ``rag_variant_id`` y ``semantic_recipe_fingerprint`` viajan solo
como provenance auditable nullable, nunca como dueños del artefacto.
"""

from __future__ import annotations

from datetime import datetime, timezone

from rag_platform.application.document_revision_service import (
    ResolveNormalizedArtifactUseCase,
)
from rag_platform.application.normalized_catalog_service import (
    PersistNormalizedArtifactCatalogRequest,
    PersistNormalizedArtifactCatalogUseCase,
)
from rag_platform.domain.artifact_catalog import NormalizedDocumentArtifactRecord
from rag_platform.domain.identity import IdentityKind, PlatformId, ProjectDocumentContext
from rag_platform.domain.models import (
    DocumentProcessingProfile,
    NormalizedDocumentArtifact,
    ProcessingOrigin,
    ProfileVerificationStatus,
    RagVariant,
    RagVariantState,
)
from rag_platform.infrastructure.in_memory.repositories import (
    InMemoryNormalizedArtifactRepository,
    InMemoryProcessingProfileRepository,
)

_PP_FP = "a" * 64
_RECIPE_FP = "c" * 64
_NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)


def _pid(kind: IdentityKind, value: str) -> PlatformId:
    return PlatformId(kind=kind, value=value)


def _profile() -> DocumentProcessingProfile:
    return DocumentProcessingProfile(
        processing_profile_id=_pid(IdentityKind.PROCESSING_PROFILE, "pp_local-pdf"),
        project_id=_pid(IdentityKind.PROJECT, "proj_sst-general"),
        provider="local",
        engine="pdfium+tesseract",
        observed_revision="2026.08.12",
        origin=ProcessingOrigin.LOCAL,
        sanitized_config={},
        fingerprint=_PP_FP,
        status=ProfileVerificationStatus.VERIFIED,
        created_at=_NOW,
    )


def _variant() -> RagVariant:
    return RagVariant(
        rag_variant_id=_pid(IdentityKind.RAG_VARIANT, "ragv_local-bge"),
        project_id=_pid(IdentityKind.PROJECT, "proj_sst-general"),
        processing_profile_id=_pid(IdentityKind.PROCESSING_PROFILE, "pp_local-pdf"),
        chunking_profile_id=_pid(IdentityKind.CHUNKING_PROFILE, "cp_structural-v1"),
        embedding_profile_id="bge-m3",
        semantic_recipe_fingerprint=_RECIPE_FP,
        state=RagVariantState.ACTIVE,
        created_at=_NOW,
    )


class _FakeVariantReader:
    """Lector de variantes por id (contrato observable de la vía Postgres)."""

    def __init__(self, variants: tuple[RagVariant, ...] = ()) -> None:
        self._by_id = {variant.rag_variant_id.value: variant for variant in variants}

    def get(self, rag_variant_id: PlatformId) -> RagVariant:
        return self._by_id[rag_variant_id.value]


class _FakeBuilder:
    """Constructor determinista de un normalizado ausente (sin motor real)."""

    def build(self, context: ProjectDocumentContext) -> NormalizedDocumentArtifact:
        return NormalizedDocumentArtifact(
            project_id=context.project_id,
            source_document_revision_id=context.source_document_revision_id,
            processing_profile_fingerprint=_PP_FP,
            schema_version="2.0",
            artifact_relpath=None,
        )


class _FakeCatalog:
    def __init__(self) -> None:
        self.rows: dict[str, NormalizedDocumentArtifactRecord] = {}
        self.upserts = 0

    def upsert(
        self, record: NormalizedDocumentArtifactRecord
    ) -> NormalizedDocumentArtifactRecord:
        self.upserts += 1
        self.rows[record.normalized_document_id] = record
        return record


def _service(
    *, variants: tuple[RagVariant, ...] = ()
) -> tuple[PersistNormalizedArtifactCatalogUseCase, _FakeCatalog]:
    resolve = ResolveNormalizedArtifactUseCase(
        artifacts=InMemoryNormalizedArtifactRepository(),
        builder=_FakeBuilder(),
        processing_profile_fingerprint=_PP_FP,
        schema_version="2.0",
    )
    catalog = _FakeCatalog()
    service = PersistNormalizedArtifactCatalogUseCase(
        resolve=resolve,
        processing_profiles=InMemoryProcessingProfileRepository((_profile(),)),
        variants=_FakeVariantReader(variants),
        catalog=catalog,
    )
    return service, catalog


def _request(
    *, rag_variant_id: str | None = None
) -> PersistNormalizedArtifactCatalogRequest:
    return PersistNormalizedArtifactCatalogRequest(
        project_id="proj_sst-general",
        source_document_id="sdoc_manual",
        source_document_revision_id="srev_manual",
        processing_profile_id="pp_local-pdf",
        source_relpath="general/manual.pdf",
        source_hash="d" * 64,
        processing_status="processed",
        rag_variant_id=rag_variant_id,
    )


def test_guarda_provenance_y_relpaths_cuando_variant_presente() -> None:
    service, catalog = _service(variants=(_variant(),))

    stored = service.execute(_request(rag_variant_id="ragv_local-bge"))

    assert stored.processing_origin == "local"
    assert stored.parser_provider == "local"
    assert stored.parser_engine == "pdfium+tesseract"
    assert stored.rag_variant_id == "ragv_local-bge"
    assert stored.semantic_recipe_fingerprint == _RECIPE_FP
    assert stored.markdown_relpath.endswith(".md")
    assert stored.metadata_relpath.endswith(".metadata.json")
    assert stored.project_id == "proj_sst-general"
    assert stored.logical_document_id == "sdoc_manual"
    # La identidad física sigue siendo project + revisión + fingerprint.
    assert stored.processing_profile_fingerprint == _PP_FP
    assert catalog.rows[stored.normalized_document_id] == stored


def test_provenance_vacia_cuando_no_hay_variant() -> None:
    service, _ = _service()

    stored = service.execute(_request())

    assert stored.rag_variant_id is None
    assert stored.semantic_recipe_fingerprint is None
    assert stored.processing_profile_fingerprint == _PP_FP


def test_normalized_document_id_es_determinista_por_identidad_fisica() -> None:
    service_a, _ = _service()
    service_b, _ = _service()

    first = service_a.execute(_request())
    second = service_b.execute(_request())

    assert first.normalized_document_id == second.normalized_document_id
    assert first.normalized_document_id.startswith("ndoc_")
