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

import json
from dataclasses import dataclass
from hashlib import sha256

from embedding.application.ports import (
    EmbeddingBundleRepository,
    EmbeddingProfileRepository,
)
from indexing.application.bundle_first.index_bundle import (
    CreateIndexingRunRequest,
    CreateIndexingRunUseCase,
    IndexingRunExecutor,
)
from indexing.application.bundle_first.ports import IndexingRunDocumentRepository
from rag_platform.application.vector_materialization import MaterializeVectorsUseCase
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import IndexingMaterialization


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
        bundles: EmbeddingBundleRepository,
        profiles: EmbeddingProfileRepository,
        materialize: MaterializeVectorsUseCase,
        storage_schema_version: str,
    ) -> None:
        self._create_indexing_run = create_indexing_run
        self._indexing_executor = indexing_executor
        self._run_documents = run_documents
        self._bundles = bundles
        self._profiles = profiles
        self._materialize = materialize
        self._storage_schema_version = storage_schema_version

    def execute(
        self,
        *,
        context: PlatformBuildContext,
        embedding_bundle_id: str,
        idempotency_key: str = "rebuild-1",
    ) -> RebuildResult:
        """Indexa el bundle y sella su materialización bajo el proyecto del contexto.

        Los parámetros de materialización (checksum, propietario, dimensión/métrica)
        se derivan server-side del propio bundle y del perfil de embedding que sirve
        el target resuelto; el caller solo aporta el contexto validado y el
        ``embedding_bundle_id``. Así ningún caller (CLI incluido) reconstruye esa
        compatibilidad a mano ni la conoce antes de indexar.

        Raises:
            NodeProjectMismatch: Si el bundle pertenece a otro proyecto.
            MaterializationSealed: Si ya hay una sellada con checksum distinto.
            MaterializationValidationFailed: Si conteos/dimensión/métrica no cuadran.
        """

        # El contexto de plataforma (validado server-side) hace el indexing run
        # release-aware: project_id/variante/release se derivan de aquí, nunca del
        # payload del cliente (plan Fase 4, runs release-aware).
        run = self._create_indexing_run.execute(
            request=CreateIndexingRunRequest(
                embedding_bundle_id=embedding_bundle_id,
                project_id=context.project_id.value,
                rag_variant_id=(
                    context.rag_variant_id.value if context.rag_variant_id else None
                ),
                rag_release_id=(
                    context.rag_release_id.value if context.rag_release_id else None
                ),
            ),
            idempotency_key=idempotency_key,
        )
        completed = self._indexing_executor.execute(run.run_id)
        if completed.indexing_target_id is None:
            raise ValueError(
                f"indexing run {completed.run_id} completed without a target"
            )
        if completed.embedding_profile_id is None:
            raise ValueError(
                f"indexing run {completed.run_id} completed without an embedding profile"
            )

        # El bundle es la autoridad del lado fuente (proyecto, dimensión, métrica); el
        # perfil que sirve el target resuelto es la autoridad del lado destino. La
        # compatibilidad la valida MaterializeVectorsUseCase (fail-closed).
        bundle = self._bundles.get(embedding_bundle_id)
        profile = self._profiles.get(completed.embedding_profile_id)

        # Conteos reales del run, agregados de sus documentos (fuente de verdad; el
        # indexado deja los vectores inactivos y aún sin materialización).
        parent, child, vectors = self._aggregate_counts(completed.run_id)

        materialization = self._materialize.materialize(
            requested_project_id=context.project_id,
            bundle_project_id=PlatformId(IdentityKind.PROJECT, bundle.project_id),
            embedding_bundle_id=embedding_bundle_id,
            indexing_target_id=completed.indexing_target_id,
            storage_schema_version=self._storage_schema_version,
            canonical_checksum=_canonical_checksum(bundle),
            parent_node_count=parent,
            child_node_count=child,
            vector_count=vectors,
            bundle_dimension=bundle.dimension,
            target_dimension=profile.dimension,
            # PhysicalDistanceMetric y DistanceMetric comparten los mismos literales
            # ("cosine"/"l2"/"inner_product"): no requiere mapeo.
            bundle_metric=bundle.distance_metric,
            target_metric=profile.distance_metric,
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


def _canonical_checksum(bundle: object) -> str:
    """Deriva un checksum canónico estable para la identidad de la materialización.

    ponytail: se colapsan los checksums de artefacto del bundle sellado (vectores,
    chunk map, manifest) más su fingerprint de contenido en un solo digest
    determinista. Es idempotente por bundle y siempre presente (el bundle ya sellado
    trae ``checksums``); no depende de un ``SealedEmbeddingStore`` aparte, porque el
    rebuild indexa bundle-first en ``idx_vec_*``, no en el store físico.
    """

    material = {
        "embedding_bundle_id": getattr(bundle, "embedding_bundle_id", ""),
        "source_content_fingerprint": getattr(bundle, "source_content_fingerprint", ""),
        "checksums": dict(sorted(getattr(bundle, "checksums", {}).items())),
    }
    return sha256(
        json.dumps(material, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
