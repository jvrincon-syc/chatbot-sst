"""Planner de build de release: reuso por identidad + construcción (Fase 5).

``BuildRagReleaseUseCase`` recorre cada revisión del corpus snapshot pinneado y, en
orden ``normalize → chunk → embed → index``, resuelve los artefactos concretos
(reusando por identidad exacta cuando existe, construyendo con los servicios
existentes cuando no). Cada etapa se audita en el ledger ``rag_build_runs``/
``rag_build_steps`` y cada revisión produce una membresía concreta.

Ponytail / DRY: el planner **no** reimplementa ingesta/chunking/embedding/indexado.
Delega la resolución de artefactos de una revisión en el puerto
``RevisionArtifactResolver``, cuyo adaptador cablea ``ArtifactReusePolicy`` (Fase 3)
y ``RebuildPlatformArtifactsUseCase`` (Fase 4). El planner solo orquesta, audita y
arma membresías, respetando el inciso del plan "invocar los servicios existentes
mediante puertos/adaptadores; no copiar sus algoritmos al módulo plataforma".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from indexing.application.bundle_first.ports import TransactionManager
from rag_platform.application.artifact_reuse_service import RagBuildRunRepository
from rag_platform.application.context import (
    PlatformAccessPolicy,
    TargetBindingResolver,
)
from rag_platform.application.platform_access import (
    PlatformActor,
    require_project_operator,
)
from rag_platform.application.release_service import (
    CorpusSnapshotReader,
    RagReleaseMembershipRepository,
    RagReleaseRepository,
    RagVariantReader,
)
from rag_platform.domain.errors import (
    IncompatibleTargetBinding,
    ReleaseBuildTooLarge,
)
from rag_platform.domain.identity import PlatformId, RagBuildContext
from rag_platform.domain.lifecycle import RagReleaseMembership
from rag_platform.domain.models import (
    BuildOutcome,
    BuildStage,
    RagVariant,
    ReuseKind,
)

#: Orden canónico de etapas de build de una revisión (plan §Fase 5).
_BUILD_STAGES: tuple[BuildStage, ...] = (
    BuildStage.NORMALIZE,
    BuildStage.CHUNK,
    BuildStage.EMBED,
    BuildStage.INDEX,
)


@dataclass(frozen=True)
class StageResolution:
    """Resultado de resolver una etapa de una revisión."""

    artifact_id: str
    outcome: BuildOutcome
    reuse_kind: ReuseKind | None = None


@dataclass(frozen=True)
class RevisionArtifacts:
    """Artefactos concretos resueltos para una revisión, etapa a etapa."""

    normalize: StageResolution
    chunk: StageResolution
    embed: StageResolution
    index: StageResolution

    def stage(self, stage: BuildStage) -> StageResolution:
        """Devuelve la resolución de una etapa por su enum."""

        return {
            BuildStage.NORMALIZE: self.normalize,
            BuildStage.CHUNK: self.chunk,
            BuildStage.EMBED: self.embed,
            BuildStage.INDEX: self.index,
        }[stage]


@runtime_checkable
class RevisionArtifactResolver(Protocol):
    """Resuelve (reuso exacto o build) los artefactos de una revisión.

    El adaptador concreto cablea ``ArtifactReusePolicy`` + los servicios existentes
    de chunking/embedding + ``RebuildPlatformArtifactsUseCase``. Falla cerrado si un
    artefacto pertenece a otro proyecto (lo imponen las guardas reusadas).
    """

    def resolve(
        self, *, context: RagBuildContext, source_document_revision_id: PlatformId
    ) -> RevisionArtifacts:
        """Devuelve los 4 artefactos concretos de la revisión bajo la receta."""


@dataclass(frozen=True)
class RagReleaseBuildReport:
    """Resumen de un build de release: membresías creadas y reusos por etapa."""

    rag_release_id: str
    revisions_built: int
    reused_stages: int
    built_stages: int


class BuildRagReleaseUseCase:
    """Construye (o reutiliza) todos los artefactos de una release DRAFT."""

    def __init__(
        self,
        *,
        releases: RagReleaseRepository,
        variants: RagVariantReader,
        snapshots: CorpusSnapshotReader,
        resolver: RevisionArtifactResolver,
        memberships: RagReleaseMembershipRepository,
        ledger: RagBuildRunRepository,
        bindings: TargetBindingResolver,
        access_policy: PlatformAccessPolicy,
        transactions: TransactionManager,
        max_build_documents: int | None = None,
    ) -> None:
        self._releases = releases
        self._variants = variants
        self._snapshots = snapshots
        self._resolver = resolver
        self._memberships = memberships
        self._ledger = ledger
        self._bindings = bindings
        self._access_policy = access_policy
        self._transactions = transactions
        # ``None`` = sin tope (comportamiento previo). Un entero positivo acota el
        # número de documentos que un build síncrono procesa por request.
        self._max_build_documents = max_build_documents

    def execute(
        self, *, rag_release_id: PlatformId, actor: PlatformActor
    ) -> RagReleaseBuildReport:
        """Recorre el snapshot, resuelve artefactos y crea membresías.

        Raises:
            PlatformAccessDenied: Si el actor no es operador o el proyecto de la
                release está fuera de su scope.
            NodeProjectMismatch / CrossProjectReuseForbidden: Si un artefacto
                resuelto pertenece a otro proyecto (fail-closed, en el resolver).
        """

        release = self._releases.get(rag_release_id)
        require_project_operator(
            policy=self._access_policy, actor=actor, project_id=release.project_id
        )
        variant = self._variants.get(release.rag_variant_id)
        snapshot = self._snapshots.get(release.corpus_snapshot_id)
        context = self._build_context(release=release, variant=variant)

        reused = 0
        built = 0
        documents = sorted(snapshot.documents, key=lambda doc: doc.ordinal)
        if (
            self._max_build_documents is not None
            and len(documents) > self._max_build_documents
        ):
            raise ReleaseBuildTooLarge(
                f"corpus snapshot has {len(documents)} documents, exceeds the "
                f"per-build limit of {self._max_build_documents}"
            )
        for document in documents:
            revision_id = document.source_document_revision_id
            # El resolver persiste/commitea los artefactos físicos por su cuenta
            # (workflow durable incremental). El build NO es una transacción global.
            artifacts = self._resolver.resolve(
                context=context, source_document_revision_id=revision_id
            )
            # UoW por revisión: ledger + membresía de esta revisión se commitean
            # juntos, dejando cada revisión durable e independiente (no hay
            # mega-transacción que sostenga toda la construcción).
            with self._transactions.transaction():
                for stage in _BUILD_STAGES:
                    resolution = artifacts.stage(stage)
                    step = self._ledger.start_step(context=context, stage=stage)
                    self._ledger.complete_step(
                        step_id=step.step_id,
                        outcome=resolution.outcome,
                        reuse_kind=resolution.reuse_kind,
                        source_artifact_id=resolution.artifact_id,
                    )
                    if resolution.outcome is BuildOutcome.REUSED:
                        reused += 1
                    elif resolution.outcome is BuildOutcome.BUILT:
                        built += 1

                self._memberships.add(
                    RagReleaseMembership(
                        rag_release_id=rag_release_id,
                        project_id=release.project_id,
                        ordinal=document.ordinal,
                        source_document_revision_id=revision_id,
                        normalized_document_id=artifacts.normalize.artifact_id,
                        chunk_bundle_id=artifacts.chunk.artifact_id,
                        embedding_bundle_id=artifacts.embed.artifact_id,
                        materialization_id=artifacts.index.artifact_id,
                    )
                )

        return RagReleaseBuildReport(
            rag_release_id=rag_release_id.value,
            revisions_built=len(documents),
            reused_stages=reused,
            built_stages=built,
        )

    def _build_context(
        self, *, release, variant: RagVariant
    ) -> RagBuildContext:
        """Deriva el ``RagBuildContext`` server-side desde la release y su variante."""

        # Deriva el target desde el binding **versionado** pinneado por la release,
        # nunca desde la configuración vigente: así el build no desvía (drift) si la
        # configuración avanzó tras crear el DRAFT (plan Task 4).
        binding = self._bindings.find_binding(
            release.project_id,
            release.configuration_version,
            release.target_binding_key,
        )
        if binding is None:
            raise IncompatibleTargetBinding(
                f"target binding {release.target_binding_key!r} is no longer allowed"
            )
        return RagBuildContext(
            project_id=release.project_id,
            rag_variant_id=release.rag_variant_id,
            rag_release_id=release.rag_release_id,
            corpus_snapshot_id=release.corpus_snapshot_id,
            embedding_profile_id=variant.embedding_profile_id,
            indexing_target_id=binding.indexing_target_id,
            semantic_recipe_fingerprint=variant.semantic_recipe_fingerprint,
        )
