"""Enriquecimiento aditivo del metadata sidecar con contexto de plataforma.

La lane legacy de ingestion produce un ``MetadataArtifact`` sin identidad de
plataforma. Cuando el pipeline corre en contexto de proyecto, este módulo le
adjunta dos bloques auditables **sin** tocar el motor de normalización:

- ``platform_identity``: proyecto, documento lógico, revisión y perfil de
  procesamiento (identidad física upstream; no depende de ``source_relpath``).
- ``platform_provenance``: variante RAG y fingerprint de la receta semántica que
  produjo el normalizado. Es provenance nullable, nunca la identidad física.

``apply_platform_metadata`` es pura: devuelve una copia enriquecida y no muta el
``MetadataArtifact`` de entrada, de modo que la vía legacy (sin contexto) queda
byte-idéntica.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Optional, Sequence

from ingestion.paths import canonical_relpath
from ingestion.schemas.artifacts import (
    MetadataArtifact,
    PlatformArtifactProvenance,
    PlatformDocumentIdentity,
)
from ingestion.schemas.common import StrictModel
from ingestion.schemas.inventory import InventoryRecord

# Identidad determinista de otro contexto acotado. Es dominio puro (solo stdlib),
# sin SDKs ni infraestructura, y sin ciclo de import. Se importa la función
# canónica en vez de duplicar la fórmula de un ID sensible a la trazabilidad.
from rag_platform.domain.identity import normalized_document_id

if TYPE_CHECKING:
    from rag_platform.domain.models import SourceDocumentRevision


class PlatformMetadataContext(StrictModel):
    """Contexto de plataforma resuelto para un documento del inventario.

    ``rag_variant_id`` y ``semantic_recipe_fingerprint`` son opcionales y viajan
    juntos: un normalizado nacido fuera de una variante no los lleva. El resto
    son la identidad física (proyecto, documento, revisión, perfil) que valida
    ``PlatformDocumentIdentity`` al aplicarse.
    """

    project_id: str
    source_document_id: str
    source_document_revision_id: str
    processing_profile_id: str
    processing_profile_fingerprint: str
    normalized_document_id: Optional[str] = None
    rag_variant_id: Optional[str] = None
    semantic_recipe_fingerprint: Optional[str] = None


def apply_platform_metadata(
    metadata: MetadataArtifact, context: PlatformMetadataContext
) -> MetadataArtifact:
    """Devuelve una copia de ``metadata`` con identidad y provenance de plataforma.

    Args:
        metadata: Metadata canónico Schema 2.0 producido por la lane legacy.
        context: Contexto de plataforma resuelto para el documento.

    Returns:
        Una copia enriquecida; el ``metadata`` original no se modifica.

    Raises:
        ValidationError: Si los identificadores del contexto están malformados o
            la provenance no viaja completa (variante y receta juntas).
    """

    identity = PlatformDocumentIdentity(
        project_id=context.project_id,
        source_document_id=context.source_document_id,
        source_document_revision_id=context.source_document_revision_id,
        normalized_document_id=context.normalized_document_id,
        processing_profile_id=context.processing_profile_id,
        processing_profile_fingerprint=context.processing_profile_fingerprint,
    )
    provenance = PlatformArtifactProvenance(
        rag_variant_id=context.rag_variant_id,
        semantic_recipe_fingerprint=context.semantic_recipe_fingerprint,
    )
    return metadata.model_copy(
        update={
            "platform_identity": identity,
            "platform_provenance": provenance,
        }
    )


class PlatformContextResolutionError(RuntimeError):
    """Un documento seleccionado no tiene revisión de plataforma registrada.

    Guarda fail-closed de la ruta normalize/promote: la identidad debe resolverse
    para *todos* los documentos seleccionados antes de leer, escribir o promover
    ninguno. El mensaje transporta el ``source_relpath`` canónico que la disparó.
    """


def resolve_platform_contexts_or_raise(
    *,
    records: Sequence[InventoryRecord],
    revisions_by_relpath: Mapping[str, "SourceDocumentRevision"],
    project_id: str,
    processing_profile_id: str,
    processing_profile_fingerprint: str,
    rag_variant_id: Optional[str],
    semantic_recipe_fingerprint: Optional[str],
) -> dict[str, PlatformMetadataContext]:
    """Resuelve la identidad de plataforma de cada documento seleccionado o falla cerrado.

    Args:
        records: Registros de inventario ya acotados a la selección de normalize.
        revisions_by_relpath: Revisiones registradas en la etapa raw, indexadas
            por ``source_relpath`` canónico.
        project_id: Proyecto dueño (``proj_...``).
        processing_profile_id: Perfil de procesamiento resuelto.
        processing_profile_fingerprint: Fingerprint de ese perfil.
        rag_variant_id: Variante de origen (provenance nullable).
        semantic_recipe_fingerprint: Receta semántica de la variante (provenance).

    Returns:
        Contextos indexados por ``source_relpath`` canónico, uno por registro
        seleccionado.

    Raises:
        PlatformContextResolutionError: Si algún registro seleccionado no tiene
            revisión registrada. Se lanza antes de leer, escribir o promover
            cualquier documento.
    """

    resolved: dict[str, PlatformMetadataContext] = {}
    for record in records:
        relpath = canonical_relpath(record.source_relpath)
        revision = revisions_by_relpath.get(relpath)
        if revision is None:
            raise PlatformContextResolutionError(relpath)
        revision_id = revision.source_document_revision_id.value
        resolved[relpath] = PlatformMetadataContext(
            project_id=project_id,
            source_document_id=revision.logical_document_id.value,
            source_document_revision_id=revision_id,
            processing_profile_id=processing_profile_id,
            processing_profile_fingerprint=processing_profile_fingerprint,
            normalized_document_id=normalized_document_id(
                project_id=project_id,
                source_document_revision_id=revision_id,
                processing_profile_fingerprint=processing_profile_fingerprint,
            ),
            rag_variant_id=rag_variant_id,
            semantic_recipe_fingerprint=semantic_recipe_fingerprint,
        )
    return resolved
