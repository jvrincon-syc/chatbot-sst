"""Bloque G — composition root del rebuild limpio de plataforma (Fase 4).

Tras el hard reset (Bloque F), los artefactos derivados se reconstruyen
**platform-only**: cada bundle nace con ``project_id`` y termina en una
materialización sellada. Este orquestador es el único punto que:

1. Deriva el contexto de plataforma (``project_id``/``rag_variant_id``/
   ``rag_release_id``) desde un ``PlatformBuildContext`` **validado en servidor**;
   nunca se acepta del payload del cliente (ADR-007 §7).
2. Encadena los casos de uso ya existentes (indexado bundle-first + materialización
   sellada) sin duplicar su lógica.
3. Falla cerrado si el bundle indexado no pertenece al proyecto del contexto o si
   los conteos/dimensión/métrica no cuadran (lo valida ``MaterializeVectorsUseCase``).

Dirección de dependencias ``dominio → aplicación``: aquí solo se conocen puertos
(los casos de uso inyectados) y modelos de dominio; ningún SDK ni BD.
"""

from __future__ import annotations

from dataclasses import dataclass

from indexing.application.bundle_first.index_bundle import (
    CreateIndexingRunRequest,
    CreateIndexingRunUseCase,
    IndexingRunExecutor,
)
from indexing.application.bundle_first.ports import IndexingRunDocumentRepository
from rag_platform.application.vector_materialization import MaterializeVectorsUseCase
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import IndexingMaterialization, PhysicalDistanceMetric


@dataclass(frozen=True)
class PlatformBuildContext:
    """Contexto de build derivado y validado en servidor (nunca del cliente).

    ``rag_variant_id``/``rag_release_id`` son opcionales: la tabla ``rag_releases``
    es de Fase 5, así que un rebuild de Fase 4 puede correr con solo ``project_id``.
    Lo que **no** es opcional es que este objeto se construya server-side desde una
    fuente confiable; el orquestador lo trata como autoridad de propiedad.
    """

    project_id: PlatformId
    rag_variant_id: PlatformId | None = None
    rag_release_id: PlatformId | None = None

    def __post_init__(self) -> None:
        # Fail-closed: el kind equivocado aquí significaría cablear una variante
        # donde se espera un proyecto. PlatformId ya valida prefijo/cuerpo.
        if self.project_id.kind is not IdentityKind.PROJECT:
            raise ValueError("project_id must be a PROJECT identity")
        if self.rag_variant_id is not None and (
            self.rag_variant_id.kind is not IdentityKind.RAG_VARIANT
        ):
            raise ValueError("rag_variant_id must be a RAG_VARIANT identity")
        if self.rag_release_id is not None and (
            self.rag_release_id.kind is not IdentityKind.RAG_RELEASE
        ):
            raise ValueError("rag_release_id must be a RAG_RELEASE identity")


@dataclass(frozen=True)
class RebuildResult:
    """Resultado de reconstruir un bundle: run indexado + materialización sellada."""

    indexing_run_id: str
    embedding_bundle_id: str
    indexing_target_id: str
    materialization: IndexingMaterialization


class RebuildPlatformArtifactsUseCase:
    """Reconstruye un embedding bundle hasta materialización sellada, platform-only.

    Reusa el indexado bundle-first (que ya namespacea nodos y persiste
    ``project_id`` cuando el chunk bundle lo trae) y luego sella la materialización
    vía :class:`MaterializeVectorsUseCase`. No indexa nada activo: el rebuild deja
    los vectores inactivos (ADR-007 §8), la activación es de una fase posterior.
    """

    def __init__(
        self,
        *,
        create_indexing_run: CreateIndexingRunUseCase,
        indexing_executor: IndexingRunExecutor,
        run_documents: IndexingRunDocumentRepository,
        materialize: MaterializeVectorsUseCase,
        storage_schema_version: str,
    ) -> None:
        self._create_indexing_run = create_indexing_run
        self._indexing_executor = indexing_executor
        self._run_documents = run_documents
        self._materialize = materialize
        self._storage_schema_version = storage_schema_version

    def execute(
        self,
        *,
        context: PlatformBuildContext,
        embedding_bundle_id: str,
        bundle_project_id: PlatformId,
        canonical_checksum: str,
        bundle_dimension: int,
        target_dimension: int,
        bundle_metric: PhysicalDistanceMetric,
        target_metric: PhysicalDistanceMetric,
        idempotency_key: str = "rebuild-1",
    ) -> RebuildResult:
        """Indexa el bundle y sella su materialización bajo el proyecto del contexto.

        Raises:
            NodeProjectMismatch: Si el bundle pertenece a otro proyecto.
            MaterializationSealed: Si ya hay una sellada con checksum distinto.
            MaterializationValidationFailed: Si conteos/dimensión/métrica no cuadran.
        """

        run = self._create_indexing_run.execute(
            request=CreateIndexingRunRequest(embedding_bundle_id=embedding_bundle_id),
            idempotency_key=idempotency_key,
        )
        completed = self._indexing_executor.execute(run.run_id)
        if completed.indexing_target_id is None:
            raise ValueError(
                f"indexing run {completed.run_id} completed without a target"
            )

        # Conteos reales del run, agregados de sus documentos (fuente de verdad; el
        # indexado deja los vectores inactivos y aún sin materialización).
        parent, child, vectors = self._aggregate_counts(completed.run_id)

        materialization = self._materialize.materialize(
            requested_project_id=context.project_id,
            bundle_project_id=bundle_project_id,
            embedding_bundle_id=embedding_bundle_id,
            indexing_target_id=completed.indexing_target_id,
            storage_schema_version=self._storage_schema_version,
            canonical_checksum=canonical_checksum,
            parent_node_count=parent,
            child_node_count=child,
            vector_count=vectors,
            bundle_dimension=bundle_dimension,
            target_dimension=target_dimension,
            bundle_metric=bundle_metric,
            target_metric=target_metric,
        )
        return RebuildResult(
            indexing_run_id=completed.run_id,
            embedding_bundle_id=embedding_bundle_id,
            indexing_target_id=completed.indexing_target_id,
            materialization=materialization,
        )

    def _aggregate_counts(self, run_id: str) -> tuple[int, int, int]:
        """Suma (parent, child, vector) de los documentos indexados del run."""

        documents = self._run_documents.list_for_run(run_id)
        parent = sum(doc.indexed_parent_nodes for doc in documents)
        child = sum(doc.indexed_child_nodes for doc in documents)
        vectors = sum(doc.vector_count for doc in documents)
        return parent, child, vectors
