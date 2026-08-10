"""Casos de uso de revisiones documentales y normalizados (Fase 2).

- ``CreateSourceDocumentRevisionUseCase``: un raw modificado crea una revisión
  **nueva** (``raw_content_hash`` distinto ⇒ ``srev_`` distinto); la anterior
  nunca se sobreescribe. Es idempotente: el mismo hash devuelve la misma revisión.
- ``ResolveNormalizedArtifactUseCase``: resuelve un normalizado por identidad
  exacta (``project + revision + processing_profile_fingerprint``) o delega la
  construcción a un puerto inyectado. No reimplementa el motor de ingesta.

Las identidades ``sdoc_``/``srev_`` se derivan de forma determinista con las
funciones de plataforma de ``ingestion.paths`` (sin tocar la legacy).
"""

from __future__ import annotations

from datetime import datetime, timezone

from ingestion.paths import platform_document_id, platform_revision_id
from ingestion.schemas.common import StrictModel
from pydantic import Field

from rag_platform.application.context import (
    NormalizedArtifactBuilder,
    NormalizedArtifactRepository,
    PlatformAccessPolicy,
    SourceDocumentRepository,
)
from rag_platform.domain.identity import (
    IdentityKind,
    PlatformId,
    ProjectDocumentContext,
)
from rag_platform.domain.models import (
    NormalizedDocumentArtifact,
    RevisionReviewState,
    SourceDocument,
    SourceDocumentRevision,
)


def _slug(project_id: PlatformId) -> str:
    return project_id.value[len(f"{IdentityKind.PROJECT.value}_") :]


class RegisterRevisionRequest(StrictModel):
    """Entrada validada para registrar una revisión documental.

    ``actor_id`` se pasa como argumento explícito del caso de uso, nunca desde el
    body (invariante §8 del plan).
    """

    project_id: str = Field(min_length=1)
    source_relpath: str = Field(min_length=1)
    raw_content_hash: str = Field(min_length=1)
    file_size: int = Field(ge=0)
    review_state: RevisionReviewState = RevisionReviewState.PROCESSED


class CreateSourceDocumentRevisionUseCase:
    """Crea (o reutiliza) una revisión inmutable para un documento lógico."""

    def __init__(
        self,
        *,
        documents: SourceDocumentRepository,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._documents = documents
        self._access_policy = access_policy

    def execute(
        self, request: RegisterRevisionRequest, *, actor_id: str
    ) -> SourceDocumentRevision:
        """Registra una revisión nueva o devuelve la existente con el mismo hash.

        Args:
            request: Datos validados de la revisión.
            actor_id: Operador autenticado; también queda como ``uploaded_by``.

        Returns:
            La ``SourceDocumentRevision`` registrada (o preexistente).
        """

        self._access_policy.require_operator(actor_id=actor_id)

        project_id = PlatformId(
            kind=IdentityKind.PROJECT,
            value=f"{IdentityKind.PROJECT.value}_{request.project_id}",
        )
        logical_id = PlatformId(
            kind=IdentityKind.SOURCE_DOCUMENT,
            value=platform_document_id(request.project_id, request.source_relpath),
        )

        now = datetime.now(timezone.utc)
        if self._documents.find_document(logical_id) is None:
            self._documents.upsert_document(
                SourceDocument(
                    logical_document_id=logical_id,
                    project_id=project_id,
                    source_relpath=request.source_relpath,
                    created_at=now,
                )
            )

        # Idempotencia: el mismo raw (mismo hash) no crea una revisión nueva.
        existing = self._documents.find_revision_by_hash(
            logical_id, request.raw_content_hash
        )
        if existing is not None:
            return existing

        revision = SourceDocumentRevision(
            source_document_revision_id=PlatformId(
                kind=IdentityKind.SOURCE_DOCUMENT_REVISION,
                value=platform_revision_id(
                    request.project_id,
                    request.source_relpath,
                    request.raw_content_hash,
                ),
            ),
            logical_document_id=logical_id,
            project_id=project_id,
            source_relpath=request.source_relpath,
            raw_content_hash=request.raw_content_hash,
            file_size=request.file_size,
            uploaded_by=actor_id,
            uploaded_at=now,
            review_state=request.review_state,
        )
        return self._documents.add_revision(revision)


class ResolveNormalizedArtifactUseCase:
    """Resuelve un normalizado por identidad exacta o lo construye vía puerto."""

    def __init__(
        self,
        *,
        artifacts: NormalizedArtifactRepository,
        builder: NormalizedArtifactBuilder,
        processing_profile_fingerprint: str,
        schema_version: str,
    ) -> None:
        self._artifacts = artifacts
        self._builder = builder
        self._fingerprint = processing_profile_fingerprint
        self._schema_version = schema_version

    def resolve_or_build(
        self, context: ProjectDocumentContext
    ) -> NormalizedDocumentArtifact:
        """Devuelve el normalizado exacto reutilizado, o lo construye una vez.

        Args:
            context: Contexto de documento (proyecto, documento, revisión, perfil).

        Returns:
            El ``NormalizedDocumentArtifact`` reutilizado o recién construido.
        """

        existing = self._artifacts.find(
            project_id=context.project_id,
            source_document_revision_id=context.source_document_revision_id,
            processing_profile_fingerprint=self._fingerprint,
        )
        if existing is not None:
            return existing

        built = self._builder.build(context)
        return self._artifacts.add(built)
