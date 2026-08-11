"""Reuso de artefactos por identidad exacta y ledger de build (Fase 3).

La plataforma reutiliza artefactos físicos exactos sin perder reproducibilidad:
los artefactos pertenecen al proyecto y una release los referencia por membresía.
El reuso automático de esta fase es **solo por identidad exacta y solo dentro del
mismo proyecto** (fail-closed, invariante §4): nunca entre proyectos aunque los
bytes coincidan.

Este módulo expone:

- ``ArtifactReusePolicy``: resuelve reuso de normalizado y de chunk bundle.
- ``RagBuildRunRepository``: puerto del ledger durable de pasos de build.
- ``ChunkBundleReuseRepository``: puerto de consulta de bundles sellados por
  identidad física.

La dirección de dependencias es ``infraestructura → aplicación → dominio``: aquí
solo se conocen puertos (Protocol) y modelos de dominio; ningún SDK ni cliente de
base de datos.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from embedding.domain.models import ChunkBundleRef
from rag_platform.application.context import NormalizedArtifactRepository
from rag_platform.domain.identity import PlatformId, RagBuildContext
from rag_platform.domain.models import (
    BuildOutcome,
    BuildStage,
    NormalizedDocumentArtifact,
    RagBuildStep,
    ReuseKind,
)


@runtime_checkable
class ChunkBundleReuseRepository(Protocol):
    """Consulta de chunk bundles sellados por identidad física exacta (§4.4)."""

    def find_sealed(
        self,
        *,
        project_id: PlatformId,
        normalized_document_id: str,
        chunking_profile_fingerprint: str,
        bundle_schema_version: str,
    ) -> ChunkBundleRef | None:
        """Devuelve el bundle sellado con esa identidad exacta, o ``None``.

        La identidad incluye ``project_id``: un bundle de otro proyecto nunca
        coincide, aunque su contenido sea idéntico.
        """


@runtime_checkable
class RagBuildRunRepository(Protocol):
    """Ledger durable de runs y pasos de build (``rag_build_runs``/``_steps``).

    El run apunta a la release; el artefacto físico no. Cada paso audita su etapa,
    resultado y, si hubo reuso, su clasificación y el artefacto origen.
    """

    def start_step(
        self, *, context: RagBuildContext, stage: BuildStage
    ) -> RagBuildStep:
        """Abre un paso para la release del contexto y devuelve su registro."""

    def complete_step(
        self,
        *,
        step_id: str,
        outcome: BuildOutcome,
        reuse_kind: ReuseKind | None = None,
        source_artifact_id: str | None = None,
    ) -> RagBuildStep:
        """Cierra un paso con su resultado y clasificación de reuso opcional."""


class ArtifactReusePolicy:
    """Resuelve reuso de artefactos por identidad exacta dentro del proyecto.

    Cada método consulta un repositorio cuya clave incluye ``project_id``, por lo
    que el reuso entre proyectos es imposible por construcción (fail-closed). Un
    reuso resuelto por estos métodos se clasifica como ``EXACT_IDENTITY``.
    """

    def __init__(
        self,
        *,
        normalized_repository: NormalizedArtifactRepository,
        chunk_bundle_repository: ChunkBundleReuseRepository,
    ) -> None:
        self._normalized = normalized_repository
        self._chunk_bundles = chunk_bundle_repository

    def find_reusable_normalized(
        self,
        *,
        project_id: PlatformId,
        source_document_revision_id: PlatformId,
        processing_profile_fingerprint: str,
    ) -> NormalizedDocumentArtifact | None:
        """Devuelve el normalizado reutilizable por identidad exacta, o ``None``."""

        return self._normalized.find(
            project_id=project_id,
            source_document_revision_id=source_document_revision_id,
            processing_profile_fingerprint=processing_profile_fingerprint,
        )

    def find_reusable_chunk_bundle(
        self,
        *,
        project_id: PlatformId,
        normalized_document_id: str,
        chunking_profile_fingerprint: str,
        bundle_schema_version: str,
    ) -> ChunkBundleRef | None:
        """Devuelve el chunk bundle sellado reutilizable, o ``None``."""

        return self._chunk_bundles.find_sealed(
            project_id=project_id,
            normalized_document_id=normalized_document_id,
            chunking_profile_fingerprint=chunking_profile_fingerprint,
            bundle_schema_version=bundle_schema_version,
        )

    # ponytail: reuso de embedding llega en Fase 4 (cambia identidad de embedding;
    # añade validación de dimensión/métrica). No se implementa aquí a propósito
    # para no dejar un NotImplemented silencioso ni un puerto sin adaptador real.
