"""Puertos y caso de uso de materialización física de vectores (Fase 4).

La materialización de vectores es propiedad del proyecto y tiene un lifecycle
inmutable ``WRITING → SEALED | FAILED`` (ADR-007 §3): una vez sellada no cambia
vectores, checksum ni conteos. El puerto expone ``find_sealed`` /
``begin_writing`` / ``seal`` / ``mark_failed`` y **nunca** un ``upsert`` sobre una
materialización sellada.

Dirección de dependencias ``infraestructura → aplicación → dominio``: aquí solo se
conocen puertos (Protocol) y modelos de dominio; ningún SDK ni cliente de BD.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from rag_platform.domain.identity import PlatformId
from rag_platform.domain.models import (
    IndexingMaterialization,
    PhysicalDistanceMetric,
    SealedEmbeddingBundle,
    ensure_materialization_sealed_is_immutable,
    validate_materialization_counts,
    validate_materialization_ownership,
)

# Nota de arquitectura (desviación deliberada respecto al plan §B-5): el escritor de
# nodos scoped por ``project_id + source_chunk_bundle_id`` vive en la lane de indexing
# (``indexing.application.bundle_first.ports.IndexingNodeWriter.replace_scoped_nodes``)
# porque escribe ``indexing_nodes`` desde ``IndexingNodeRecord`` (registro completo con
# texto/metadata). Duplicar aquí un puerto que tomara el ``PhysicalNode`` lean obligaría
# a un segundo mapeo del mismo row; se consume el puerto de indexing (DRY, sin cruzar
# responsabilidades de capacidad).


@runtime_checkable
class SealedEmbeddingStore(Protocol):
    """Almacén físico de embeddings sellados por proyecto (content-addressed)."""

    def stage_and_seal(
        self,
        *,
        project_id: PlatformId,
        embedding_bundle_id: str,
        source_chunk_bundle_id: str,
        dimension: int,
        distance_metric: PhysicalDistanceMetric,
        manifest: dict[str, object],
        vectors: Sequence[Sequence[float]],
        chunk_map: Sequence[dict[str, object]],
    ) -> SealedEmbeddingBundle:
        """Sella un embedding bundle de forma atómica e idempotente."""

    def verify_checksum(
        self,
        *,
        project_id: PlatformId,
        embedding_bundle_id: str,
        expected: dict[str, str],
    ) -> bool:
        """Recomputa checksums del artefacto sellado y los compara."""


@runtime_checkable
class IndexingMaterializationRepository(Protocol):
    """Repositorio del lifecycle inmutable de materializaciones (ADR-007 §3)."""

    def find_sealed(
        self,
        *,
        project_id: PlatformId,
        embedding_bundle_id: str,
        indexing_target_id: str,
        storage_schema_version: str,
    ) -> IndexingMaterialization | None:
        """Devuelve la materialización sellada con esa identidad, o ``None``."""

    def begin_writing(
        self,
        *,
        project_id: PlatformId,
        embedding_bundle_id: str,
        indexing_target_id: str,
        storage_schema_version: str,
    ) -> IndexingMaterialization:
        """Abre una materialización en estado ``WRITING``."""

    def seal(
        self,
        *,
        materialization_id: str,
        canonical_checksum: str,
        parent_node_count: int,
        child_node_count: int,
        vector_count: int,
    ) -> IndexingMaterialization:
        """Sella una materialización ``WRITING`` fijando checksum y conteos."""

    def mark_failed(
        self, *, materialization_id: str, failure_code: str
    ) -> IndexingMaterialization:
        """Marca una materialización como ``FAILED`` con un código observable."""


class MaterializeVectorsUseCase:
    """Materializa vectores de un bundle en un target con validación transaccional.

    El flujo es fail-closed:

    1. Si ya existe una materialización sellada con el mismo checksum, la devuelve
       (idempotente); si está sellada con otro checksum, ``MaterializationSealed``.
    2. Abre ``WRITING``, valida owner/dimensión/métrica/conteos; si algo falla, marca
       ``FAILED`` con ``failure_code`` observable y re-lanza el error de dominio.
    3. Solo si todo cuadra, sella (``SEALED``) fijando checksum y conteos.
    """

    def __init__(self, *, repository: IndexingMaterializationRepository) -> None:
        self._repository = repository

    def materialize(
        self,
        *,
        requested_project_id: PlatformId,
        bundle_project_id: PlatformId,
        embedding_bundle_id: str,
        indexing_target_id: str,
        storage_schema_version: str,
        canonical_checksum: str,
        parent_node_count: int,
        child_node_count: int,
        vector_count: int,
        bundle_dimension: int,
        target_dimension: int,
        bundle_metric: PhysicalDistanceMetric,
        target_metric: PhysicalDistanceMetric,
    ) -> IndexingMaterialization:
        """Materializa un bundle o devuelve la materialización sellada existente.

        Raises:
            MaterializationSealed: Si ya hay una sellada con checksum distinto.
            NodeProjectMismatch: Si el bundle pertenece a otro proyecto.
            MaterializationValidationFailed: Si conteos/dimensión/métrica no cuadran.
        """

        existing = self._repository.find_sealed(
            project_id=requested_project_id,
            embedding_bundle_id=embedding_bundle_id,
            indexing_target_id=indexing_target_id,
            storage_schema_version=storage_schema_version,
        )
        if ensure_materialization_sealed_is_immutable(
            existing, canonical_checksum=canonical_checksum
        ):
            assert existing is not None  # narrow para el type-checker
            return existing

        materialization = self._repository.begin_writing(
            project_id=requested_project_id,
            embedding_bundle_id=embedding_bundle_id,
            indexing_target_id=indexing_target_id,
            storage_schema_version=storage_schema_version,
        )
        try:
            validate_materialization_ownership(
                requested_project_id=requested_project_id,
                bundle_project_id=bundle_project_id,
            )
            validate_materialization_counts(
                parent_node_count=parent_node_count,
                child_node_count=child_node_count,
                vector_count=vector_count,
                target_dimension=target_dimension,
                bundle_dimension=bundle_dimension,
                target_metric=target_metric,
                bundle_metric=bundle_metric,
            )
        except Exception as error:
            # Borde de validación: deja la materialización FAILED (observable y
            # reanudable) y preserva la causa. No se sella nada a medias.
            failure_code = getattr(error, "code", type(error).__name__)
            self._repository.mark_failed(
                materialization_id=materialization.materialization_id,
                failure_code=str(failure_code),
            )
            raise

        return self._repository.seal(
            materialization_id=materialization.materialization_id,
            canonical_checksum=canonical_checksum,
            parent_node_count=parent_node_count,
            child_node_count=child_node_count,
            vector_count=vector_count,
        )
