"""In-memory resolver operativo para builds de release (Fase 5).

Reemplaza el doble ad hoc de los tests con una implementación in-memory que
persiste el resultado resuelto por identidad de build. Un segundo build con la
misma receta/target reutiliza exactamente los artefactos previamente
materializados para esa revisión.
"""

from __future__ import annotations

from rag_platform.application.release_build_service import (
    RevisionArtifacts,
    StageResolution,
)
from rag_platform.domain.identity import PlatformId, RagBuildContext
from rag_platform.domain.models import BuildOutcome, ReuseKind


class InMemoryRevisionArtifactResolver:
    """Resolver in-memory con reuso exacto por identidad operacional."""

    def __init__(self) -> None:
        self._artifacts_by_identity: dict[tuple[str, ...], RevisionArtifacts] = {}

    def resolve(
        self, *, context: RagBuildContext, source_document_revision_id: PlatformId
    ) -> RevisionArtifacts:
        key = self._identity(
            context=context, source_document_revision_id=source_document_revision_id
        )
        existing = self._artifacts_by_identity.get(key)
        if existing is not None:
            return self._as_reused(existing)

        built = self._build_artifacts(source_document_revision_id)
        self._artifacts_by_identity[key] = built
        return built

    @staticmethod
    def _identity(
        *, context: RagBuildContext, source_document_revision_id: PlatformId
    ) -> tuple[str, ...]:
        return (
            context.project_id.value,
            context.rag_variant_id.value,
            context.embedding_profile_id,
            context.indexing_target_id,
            context.semantic_recipe_fingerprint,
            source_document_revision_id.value,
        )

    @staticmethod
    def _build_artifacts(source_document_revision_id: PlatformId) -> RevisionArtifacts:
        revision = source_document_revision_id.value
        return RevisionArtifacts(
            normalize=StageResolution(
                artifact_id=f"norm_{revision}",
                outcome=BuildOutcome.BUILT,
            ),
            chunk=StageResolution(
                artifact_id=f"chunk_{revision}",
                outcome=BuildOutcome.BUILT,
            ),
            embed=StageResolution(
                artifact_id=f"emb_{revision}",
                outcome=BuildOutcome.BUILT,
            ),
            index=StageResolution(
                artifact_id=f"mat_{revision}",
                outcome=BuildOutcome.BUILT,
            ),
        )

    @staticmethod
    def _as_reused(artifacts: RevisionArtifacts) -> RevisionArtifacts:
        return RevisionArtifacts(
            normalize=StageResolution(
                artifact_id=artifacts.normalize.artifact_id,
                outcome=BuildOutcome.REUSED,
                reuse_kind=ReuseKind.EXACT_IDENTITY,
            ),
            chunk=StageResolution(
                artifact_id=artifacts.chunk.artifact_id,
                outcome=BuildOutcome.REUSED,
                reuse_kind=ReuseKind.EXACT_IDENTITY,
            ),
            embed=StageResolution(
                artifact_id=artifacts.embed.artifact_id,
                outcome=BuildOutcome.REUSED,
                reuse_kind=ReuseKind.EXACT_IDENTITY,
            ),
            index=StageResolution(
                artifact_id=artifacts.index.artifact_id,
                outcome=BuildOutcome.REUSED,
                reuse_kind=ReuseKind.EXACT_IDENTITY,
            ),
        )
