"""Fase 3: reuso por identidad exacta dentro del proyecto y ledger de build.

Cubre:
- reuso de chunk bundle por identidad exacta dentro del proyecto;
- ausencia de reuso entre proyectos aunque los bytes coincidan (fail-closed);
- reuso de normalizado por identidad exacta e identidad ausente;
- clasificación de reuso y guarda cross-proyecto (incluido ``operator_approved``);
- registro de pasos en el ledger;
- exit criteria: ``release-002`` con un documento adicional reutiliza N-1 bundles
  por identidad exacta y construye 1 nuevo.
"""

from __future__ import annotations

import pytest

from embedding.domain.models import ChunkBundleRef
from rag_platform.application.artifact_reuse_service import ArtifactReusePolicy
from rag_platform.domain.errors import BuildStepNotFound, CrossProjectReuseForbidden
from rag_platform.domain.identity import IdentityKind, PlatformId, RagBuildContext
from rag_platform.domain.models import (
    BuildOutcome,
    BuildStage,
    NormalizedDocumentArtifact,
    ReuseKind,
    ensure_reuse_within_project,
)
from rag_platform.infrastructure.in_memory.repositories import (
    InMemoryChunkBundleReuseRepository,
    InMemoryNormalizedArtifactRepository,
    InMemoryRagBuildRunRepository,
)


_FINGERPRINT = "a" * 64
_SCHEMA = "sealed-v1"


def _project(slug: str) -> PlatformId:
    return PlatformId(IdentityKind.PROJECT, f"proj_{slug}")


def _revision(body: str) -> PlatformId:
    return PlatformId(IdentityKind.SOURCE_DOCUMENT_REVISION, f"srev_{body}")


def _ref(bundle_id: str) -> ChunkBundleRef:
    return ChunkBundleRef(
        chunk_bundle_id=bundle_id,
        bundle_fingerprint=bundle_id,
        profile_id="local-structural-v1",
        profile_fingerprint=_FINGERPRINT,
        corpus_version="phase1",
        source_document_id="ndoc_01",
        artifact_relpath=f"chunks/{bundle_id}/manifest.json",
        parent_count=1,
        child_count=1,
        status="verified",
    )


def _context(*, project: str, release: str) -> RagBuildContext:
    return RagBuildContext(
        project_id=_project(project),
        rag_variant_id=PlatformId(IdentityKind.RAG_VARIANT, "ragv_local-bge-m3"),
        rag_release_id=PlatformId(IdentityKind.RAG_RELEASE, f"ragr_{release}"),
        corpus_snapshot_id=PlatformId(IdentityKind.CORPUS_SNAPSHOT, "corpus_sst002"),
        embedding_profile_id="bge-m3-v1",
        indexing_target_id="local-bge-primary",
        semantic_recipe_fingerprint=_FINGERPRINT,
    )


def _policy() -> tuple[ArtifactReusePolicy, InMemoryChunkBundleReuseRepository, InMemoryNormalizedArtifactRepository]:
    chunk_repo = InMemoryChunkBundleReuseRepository()
    normalized_repo = InMemoryNormalizedArtifactRepository()
    policy = ArtifactReusePolicy(
        normalized_repository=normalized_repo,
        chunk_bundle_repository=chunk_repo,
    )
    return policy, chunk_repo, normalized_repo


def test_reutiliza_chunk_bundle_cuando_identidad_exacta_en_mismo_proyecto() -> None:
    policy, chunk_repo, _ = _policy()
    project = _project("sst-general")
    chunk_repo.register_sealed(
        _ref("cb_01"),
        project_id=project,
        normalized_document_id="ndoc_01",
        chunking_profile_fingerprint=_FINGERPRINT,
        bundle_schema_version=_SCHEMA,
    )

    found = policy.find_reusable_chunk_bundle(
        project_id=project,
        normalized_document_id="ndoc_01",
        chunking_profile_fingerprint=_FINGERPRINT,
        bundle_schema_version=_SCHEMA,
    )

    assert found is not None
    assert found.chunk_bundle_id == "cb_01"


def test_no_reutiliza_chunk_bundle_entre_proyectos_con_bytes_iguales() -> None:
    policy, chunk_repo, _ = _policy()
    chunk_repo.register_sealed(
        _ref("cb_01"),
        project_id=_project("sst-general"),
        normalized_document_id="ndoc_01",
        chunking_profile_fingerprint=_FINGERPRINT,
        bundle_schema_version=_SCHEMA,
    )

    found = policy.find_reusable_chunk_bundle(
        project_id=_project("calidad-interna"),
        normalized_document_id="ndoc_01",
        chunking_profile_fingerprint=_FINGERPRINT,
        bundle_schema_version=_SCHEMA,
    )

    assert found is None


def test_reutiliza_normalizado_cuando_identidad_exacta_y_none_cuando_ausente() -> None:
    policy, _, normalized_repo = _policy()
    project = _project("sst-general")
    revision = _revision("doc01")
    normalized_repo.add(
        NormalizedDocumentArtifact(
            project_id=project,
            source_document_revision_id=revision,
            processing_profile_fingerprint=_FINGERPRINT,
            schema_version="2.0",
            artifact_relpath="normalized/doc01.md",
        )
    )

    hit = policy.find_reusable_normalized(
        project_id=project,
        source_document_revision_id=revision,
        processing_profile_fingerprint=_FINGERPRINT,
    )
    miss = policy.find_reusable_normalized(
        project_id=project,
        source_document_revision_id=_revision("doc99"),
        processing_profile_fingerprint=_FINGERPRINT,
    )

    assert hit is not None
    assert miss is None


def test_operator_approved_no_puede_reutilizar_entre_proyectos() -> None:
    with pytest.raises(CrossProjectReuseForbidden):
        ensure_reuse_within_project(
            requested_project_id=_project("calidad-interna"),
            source_project_id=_project("sst-general"),
            reuse_kind=ReuseKind.OPERATOR_APPROVED,
        )


def test_ledger_registra_pasos_de_build_con_clasificacion_de_reuso() -> None:
    ledger = InMemoryRagBuildRunRepository()
    context = _context(project="sst-general", release="r002")

    step = ledger.start_step(context=context, stage=BuildStage.CHUNK)
    completed = ledger.complete_step(
        step_id=step.step_id,
        outcome=BuildOutcome.REUSED,
        reuse_kind=ReuseKind.EXACT_IDENTITY,
        source_artifact_id="cb_01",
    )

    assert completed.outcome is BuildOutcome.REUSED
    assert completed.reuse_kind is ReuseKind.EXACT_IDENTITY
    assert completed.source_artifact_id == "cb_01"
    assert completed.completed_at is not None
    steps = ledger.steps_for(context.rag_release_id)
    assert len(steps) == 1
    assert steps[0].stage is BuildStage.CHUNK


def test_complete_step_falla_cerrado_cuando_el_paso_no_existe() -> None:
    ledger = InMemoryRagBuildRunRepository()
    with pytest.raises(BuildStepNotFound):
        ledger.complete_step(step_id="rbs_inexistente", outcome=BuildOutcome.BUILT)


def test_release_002_reutiliza_55_bundles_y_construye_uno_nuevo() -> None:
    policy, chunk_repo, _ = _policy()
    ledger = InMemoryRagBuildRunRepository()
    project = _project("sst-general")
    context = _context(project="sst-general", release="r002")

    # release-001 selló 55 bundles; el documento 56 es nuevo.
    reused_docs = [f"ndoc_{index:02d}" for index in range(1, 56)]
    for doc_id in reused_docs:
        chunk_repo.register_sealed(
            _ref(f"cb_{doc_id}"),
            project_id=project,
            normalized_document_id=doc_id,
            chunking_profile_fingerprint=_FINGERPRINT,
            bundle_schema_version=_SCHEMA,
        )
    corpus_002 = reused_docs + ["ndoc_56"]

    reused = 0
    built = 0
    for doc_id in corpus_002:
        step = ledger.start_step(context=context, stage=BuildStage.CHUNK)
        found = policy.find_reusable_chunk_bundle(
            project_id=project,
            normalized_document_id=doc_id,
            chunking_profile_fingerprint=_FINGERPRINT,
            bundle_schema_version=_SCHEMA,
        )
        if found is not None:
            ledger.complete_step(
                step_id=step.step_id,
                outcome=BuildOutcome.REUSED,
                reuse_kind=ReuseKind.EXACT_IDENTITY,
                source_artifact_id=found.chunk_bundle_id,
            )
            reused += 1
        else:
            ledger.complete_step(step_id=step.step_id, outcome=BuildOutcome.BUILT)
            built += 1

    assert reused == 55
    assert built == 1
    steps = ledger.steps_for(context.rag_release_id)
    assert len(steps) == 56
    assert sum(1 for s in steps if s.reuse_kind is ReuseKind.EXACT_IDENTITY) == 55
