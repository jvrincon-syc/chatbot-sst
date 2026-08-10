"""Fase 2: revisiones documentales inmutables y reuso de normalizados."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rag_platform.application.document_revision_service import (
    CreateSourceDocumentRevisionUseCase,
    RegisterRevisionRequest,
    ResolveNormalizedArtifactUseCase,
)
from rag_platform.domain.identity import (
    IdentityKind,
    PlatformId,
    ProjectDocumentContext,
)
from rag_platform.domain.models import NormalizedDocumentArtifact, RevisionReviewState
from rag_platform.infrastructure.in_memory.repositories import (
    AllowAllAccessPolicy,
    InMemoryNormalizedArtifactRepository,
    InMemorySourceDocumentRepository,
)

_FP = "a" * 64


def _use_case() -> tuple[
    CreateSourceDocumentRevisionUseCase, InMemorySourceDocumentRepository
]:
    documents = InMemorySourceDocumentRepository()
    return (
        CreateSourceDocumentRevisionUseCase(
            documents=documents, access_policy=AllowAllAccessPolicy()
        ),
        documents,
    )


def test_raw_modificado_crea_revision_nueva_sin_sobreescribir() -> None:
    use_case, _ = _use_case()
    first = use_case.execute(
        RegisterRevisionRequest(
            project_id="sst-general",
            source_relpath="manual/x.pdf",
            raw_content_hash="hash-v1",
            file_size=10,
        ),
        actor_id="op-1",
    )
    second = use_case.execute(
        RegisterRevisionRequest(
            project_id="sst-general",
            source_relpath="manual/x.pdf",
            raw_content_hash="hash-v2",  # bytes cambiados
            file_size=11,
        ),
        actor_id="op-1",
    )

    assert first.source_document_revision_id != second.source_document_revision_id
    assert first.logical_document_id == second.logical_document_id  # mismo doc lógico


def test_mismo_raw_es_idempotente() -> None:
    use_case, _ = _use_case()
    args = RegisterRevisionRequest(
        project_id="sst-general",
        source_relpath="manual/x.pdf",
        raw_content_hash="hash-v1",
        file_size=10,
    )
    first = use_case.execute(args, actor_id="op-1")
    again = use_case.execute(args, actor_id="op-2")

    assert first.source_document_revision_id == again.source_document_revision_id
    # La revisión es inmutable: conserva el actor original.
    assert again.uploaded_by == "op-1"


def test_dos_proyectos_mismo_relpath_no_colisionan() -> None:
    use_case, _ = _use_case()
    a = use_case.execute(
        RegisterRevisionRequest(
            project_id="sst-general",
            source_relpath="manual/x.pdf",
            raw_content_hash="same-bytes",
            file_size=10,
        ),
        actor_id="op-1",
    )
    b = use_case.execute(
        RegisterRevisionRequest(
            project_id="calidad-interna",
            source_relpath="manual/x.pdf",  # misma ruta relativa
            raw_content_hash="same-bytes",  # incluso mismos bytes
            file_size=10,
        ),
        actor_id="op-1",
    )

    assert a.logical_document_id != b.logical_document_id
    assert a.source_document_revision_id != b.source_document_revision_id


class _RecordingBuilder:
    """Builder de normalizado que cuenta cuántas veces construye."""

    def __init__(self) -> None:
        self.calls = 0

    def build(self, context: ProjectDocumentContext) -> NormalizedDocumentArtifact:
        self.calls += 1
        return NormalizedDocumentArtifact(
            project_id=context.project_id,
            source_document_revision_id=context.source_document_revision_id,
            processing_profile_fingerprint=_FP,
            schema_version="2.0",
        )


def _context() -> ProjectDocumentContext:
    return ProjectDocumentContext(
        project_id=PlatformId(kind=IdentityKind.PROJECT, value="proj_sst-general"),
        source_document_id=PlatformId(
            kind=IdentityKind.SOURCE_DOCUMENT, value="sdoc_abc"
        ),
        source_document_revision_id=PlatformId(
            kind=IdentityKind.SOURCE_DOCUMENT_REVISION, value="srev_abc"
        ),
        processing_profile_id=PlatformId(
            kind=IdentityKind.PROCESSING_PROFILE, value="pp_local"
        ),
    )


def test_resolve_normalizado_reutiliza_por_identidad_exacta() -> None:
    builder = _RecordingBuilder()
    use_case = ResolveNormalizedArtifactUseCase(
        artifacts=InMemoryNormalizedArtifactRepository(),
        builder=builder,
        processing_profile_fingerprint=_FP,
        schema_version="2.0",
    )
    context = _context()

    built = use_case.resolve_or_build(context)
    reused = use_case.resolve_or_build(context)

    assert builder.calls == 1  # el segundo resolve reutiliza, no reconstruye
    assert built == reused
