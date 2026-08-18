"""Lifecycle de releases de plataforma RAG (Fase 5).

Una ``RagRelease`` congela una variante (receta) sobre un corpus snapshot y un
target binding pinneado. Su lifecycle es estricto e inmutable en sitio:

``DRAFT → VALIDATED → PUBLISHED → RETIRED`` (más ``FAILED`` como terminal de fallo).

Separación de semánticas (criterio del plan, ADR-006 §3):

- ``VALIDATED`` = la release está completa y su ``release_manifest_hash`` quedó
  congelado; **no** significa publicada ni activa.
- ``PUBLISHED`` (Fase 6) = el catálogo de plataforma la acepta; **no** toca
  ``is_active`` ni ``retrieval_profiles`` legacy.
- La activación legacy es un concepto aparte que este módulo nunca escribe.

Dominio puro: sin SDK ni SQL. Reusa ``StrictModel`` y las identidades tipadas de
``rag_platform.domain.models`` para no redefinir contratos.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import hashlib
import json
from typing import Mapping, Sequence

from pydantic import Field

from ingestion.schemas.common import StrictModel
from rag_platform.domain.errors import (
    InvalidReleaseTransition,
    ReleaseProjectMismatch,
)
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.models import (
    CorpusSnapshotId,
    ProjectId,
    RagReleaseId,
    RagVariantId,
    SourceDocumentRevisionId,
)


class ReleaseState(str, Enum):
    """Estados del lifecycle de una release (ADR-006 §3).

    ``FAILED`` es terminal: un build que no completa deja la release observable
    como fallida, nunca a medias en ``DRAFT``.
    """

    DRAFT = "draft"
    VALIDATED = "validated"
    PUBLISHED = "published"
    RETIRED = "retired"
    FAILED = "failed"


#: Transiciones permitidas. Cualquier par fuera de este grafo es fail-closed.
_ALLOWED_TRANSITIONS: Mapping[ReleaseState, frozenset[ReleaseState]] = {
    ReleaseState.DRAFT: frozenset({ReleaseState.VALIDATED, ReleaseState.FAILED}),
    ReleaseState.VALIDATED: frozenset(
        {ReleaseState.PUBLISHED, ReleaseState.FAILED, ReleaseState.RETIRED}
    ),
    ReleaseState.PUBLISHED: frozenset({ReleaseState.RETIRED}),
    ReleaseState.RETIRED: frozenset(),
    ReleaseState.FAILED: frozenset(),
}


def ensure_transition_allowed(
    *, current: ReleaseState, target: ReleaseState
) -> None:
    """Valida una transición de estado de release (fail-closed).

    Args:
        current: Estado actual de la release.
        target: Estado destino solicitado.

    Raises:
        InvalidReleaseTransition: Si el par ``(current, target)`` no está en el
            grafo permitido.
    """

    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidReleaseTransition(
            f"transition {current.value} -> {target.value} is not allowed"
        )


class RagReleaseMembership(StrictModel):
    """Membresía concreta de una revisión en una release.

    Ancla la revisión a los artefactos físicos construidos/reutilizados para ella
    (normalizado, chunk bundle, embedding bundle, materialización). Todos son
    propiedad del mismo proyecto que la release; un artefacto de otro proyecto es
    fail-closed en el validador de la release.
    """

    rag_release_id: RagReleaseId
    project_id: ProjectId
    ordinal: int = Field(ge=0)
    source_document_revision_id: SourceDocumentRevisionId
    normalized_document_id: str = Field(min_length=1)
    chunk_bundle_id: str = Field(min_length=1)
    embedding_bundle_id: str = Field(min_length=1)
    materialization_id: str = Field(min_length=1)


class RagRelease(StrictModel):
    """Release inmutable de una variante sobre un corpus snapshot.

    ``release_number`` es único dentro de la variante (nunca global del proyecto);
    la unicidad la impone un índice único parcial en la BD. ``release_manifest_hash``
    se congela al validar y es reconstruible con los hashes que lo componen.
    """

    rag_release_id: RagReleaseId
    project_id: ProjectId
    rag_variant_id: RagVariantId
    corpus_snapshot_id: CorpusSnapshotId
    target_binding_key: str = Field(min_length=1, max_length=128)
    # Única identidad nueva persistida (plan Task 4): pinnea la versión exacta de
    # configuración vigente al crear el DRAFT. El ``indexing_target`` NO se
    # persiste en la release; se DERIVA del binding versionado
    # ``(project_id, configuration_version, target_binding_key)``, de modo que un
    # cambio posterior de configuración no puede desviar (drift) la release ya
    # pinneada.
    configuration_version: int = Field(ge=1)
    release_number: int = Field(ge=1)
    state: ReleaseState = ReleaseState.DRAFT
    release_manifest_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    created_by: str = Field(min_length=1)
    created_at: datetime
    validated_at: datetime | None = None
    reason: str | None = None

    @property
    def is_manifest_frozen(self) -> bool:
        """Return whether the manifest hash was already frozen (state >= VALIDATED)."""

        return self.release_manifest_hash is not None


def compute_release_manifest_hash(
    *,
    project_id: str,
    rag_variant_id: str,
    corpus_snapshot_id: str,
    corpus_manifest_hash: str,
    semantic_recipe_fingerprint: str,
    configuration_fingerprint: str,
    target_binding_key: str,
    memberships: Sequence[RagReleaseMembership],
) -> str:
    """Computa el ``release_manifest_hash`` determinista de una release.

    Espeja :func:`compute_corpus_manifest_hash`: depende solo de los hashes de
    entrada (snapshot, receta, configuración, target) y de la lista ordenada de
    membresías con sus artefactos concretos. Reconstruible únicamente con las filas
    persistidas; agregar/quitar/reemplazar una membresía cambia el hash.

    Args:
        project_id: Valor textual del ``project_id`` propietario.
        rag_variant_id: Valor textual de la variante.
        corpus_snapshot_id: Valor textual del snapshot pinneado.
        corpus_manifest_hash: Hash del corpus snapshot (ya reconstruible).
        semantic_recipe_fingerprint: Fingerprint de la receta de la variante.
        configuration_fingerprint: Fingerprint de la configuración del proyecto.
        target_binding_key: Binding key permitido resuelto para la release.
        memberships: Membresías en su orden final (por ``ordinal``).

    Returns:
        Digest hex sha256 de 64 caracteres.
    """

    payload = {
        "project_id": project_id,
        "rag_variant_id": rag_variant_id,
        "corpus_snapshot_id": corpus_snapshot_id,
        "corpus_manifest_hash": corpus_manifest_hash,
        "semantic_recipe_fingerprint": semantic_recipe_fingerprint,
        "configuration_fingerprint": configuration_fingerprint,
        "target_binding_key": target_binding_key,
        "memberships": [
            {
                "ordinal": member.ordinal,
                "revision_id": member.source_document_revision_id.value,
                "normalized_document_id": member.normalized_document_id,
                "chunk_bundle_id": member.chunk_bundle_id,
                "embedding_bundle_id": member.embedding_bundle_id,
                "materialization_id": member.materialization_id,
            }
            for member in sorted(memberships, key=lambda member: member.ordinal)
        ],
    }
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def next_release_number(*, existing_numbers: Sequence[int]) -> int:
    """Return the next per-variant release number (max + 1, or 1 when empty).

    La unicidad real la garantiza el índice parcial de la BD; esta función solo
    sugiere el siguiente número de forma determinista.
    """

    return (max(existing_numbers) + 1) if existing_numbers else 1


def ensure_same_project(
    *, variant_project_id: PlatformId, snapshot_project_id: PlatformId
) -> None:
    """Valida que variante y snapshot son del mismo proyecto (fail-closed).

    Raises:
        ReleaseProjectMismatch: Si los proyectos difieren.
    """

    if variant_project_id != snapshot_project_id:
        raise ReleaseProjectMismatch(
            "variant and corpus snapshot belong to different projects: "
            f"{variant_project_id.value} != {snapshot_project_id.value}"
        )
