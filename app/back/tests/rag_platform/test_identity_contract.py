"""Fase 0: el contrato de identidad de plataforma no es intercambiable."""

from __future__ import annotations

import pytest

from rag_platform.domain.identity import (
    IdentityKind,
    InvalidIdentity,
    PlatformId,
    ProjectDocumentContext,
    RagBuildContext,
)


def _pid(kind: IdentityKind, body: str = "01") -> PlatformId:
    return PlatformId(kind=kind, value=f"{kind.value}_{body}")


def test_platform_ids_of_different_kind_never_equal_cuando_comparten_cuerpo() -> None:
    project = _pid(IdentityKind.PROJECT, "sst-general")
    variant = PlatformId(kind=IdentityKind.RAG_VARIANT, value="ragv_sst-general")

    # Mismo cuerpo textual "sst-general" pero clases distintas: no colisionan.
    assert project != variant
    assert project.value != variant.value


def test_parse_falla_cerrado_cuando_prefijo_no_corresponde() -> None:
    with pytest.raises(InvalidIdentity):
        PlatformId.parse(IdentityKind.RAG_RELEASE, "ragv_local-bge-m3")


def test_parse_falla_cerrado_cuando_cuerpo_es_malformado() -> None:
    with pytest.raises(InvalidIdentity):
        PlatformId.parse(IdentityKind.PROJECT, "proj_Con Espacios")


def test_build_context_rechaza_variante_donde_se_espera_release() -> None:
    variant_masquerading_as_release = _pid(IdentityKind.RAG_VARIANT)
    with pytest.raises(InvalidIdentity):
        RagBuildContext(
            project_id=_pid(IdentityKind.PROJECT),
            rag_variant_id=_pid(IdentityKind.RAG_VARIANT),
            rag_release_id=variant_masquerading_as_release,  # clase equivocada
            corpus_snapshot_id=_pid(IdentityKind.CORPUS_SNAPSHOT),
            embedding_profile_id="emb-bge-m3",
            indexing_target_id="tgt-local",
            semantic_recipe_fingerprint="deadbeef",
        )


def test_build_context_exige_recipe_fingerprint_no_vacio() -> None:
    with pytest.raises(InvalidIdentity):
        RagBuildContext(
            project_id=_pid(IdentityKind.PROJECT),
            rag_variant_id=_pid(IdentityKind.RAG_VARIANT),
            rag_release_id=_pid(IdentityKind.RAG_RELEASE),
            corpus_snapshot_id=_pid(IdentityKind.CORPUS_SNAPSHOT),
            embedding_profile_id="emb-bge-m3",
            indexing_target_id="tgt-local",
            semantic_recipe_fingerprint="",
        )


def test_document_context_no_depende_solo_de_source_relpath() -> None:
    # La identidad válida requiere las cuatro clases; ninguna es el relpath.
    context = ProjectDocumentContext(
        project_id=_pid(IdentityKind.PROJECT),
        source_document_id=_pid(IdentityKind.SOURCE_DOCUMENT),
        source_document_revision_id=_pid(IdentityKind.SOURCE_DOCUMENT_REVISION),
        processing_profile_id=_pid(IdentityKind.PROCESSING_PROFILE),
    )
    assert context.project_id.kind is IdentityKind.PROJECT

    # Sustituir una clase por otra (revisión por proyecto) falla cerrado.
    with pytest.raises(InvalidIdentity):
        ProjectDocumentContext(
            project_id=_pid(IdentityKind.PROJECT),
            source_document_id=_pid(IdentityKind.SOURCE_DOCUMENT),
            source_document_revision_id=_pid(IdentityKind.PROJECT),  # clase equivocada
            processing_profile_id=_pid(IdentityKind.PROCESSING_PROFILE),
        )
