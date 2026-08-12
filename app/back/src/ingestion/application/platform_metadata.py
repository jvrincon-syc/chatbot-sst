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

from typing import Optional

from ingestion.schemas.artifacts import (
    MetadataArtifact,
    PlatformArtifactProvenance,
    PlatformDocumentIdentity,
)
from ingestion.schemas.common import StrictModel


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
