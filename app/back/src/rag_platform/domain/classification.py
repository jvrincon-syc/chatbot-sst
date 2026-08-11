"""Clasificación documental de plataforma: resultado y resolución de tipo (Fase 2).

Separa dos responsabilidades del texto del plan (§Fase 2, política documental):

- ``DocumentClassificationResult`` es el contrato de salida neutral de plataforma.
  No usa el ``Literal`` legacy: su ``document_type`` es un ``code`` que debe existir
  en el catálogo versionado del proyecto.
- ``resolve_document_type`` valida ese ``code`` contra la configuración del
  proyecto de forma **fail-closed**: si el tipo no está permitido, lanza
  ``DocumentTypeNotPermitted`` en vez de degradar a la ruta legacy.

El motor concreto de reglas SST permanece en ``ingestion.classification.rules`` y
se envuelve en un adaptador de infraestructura; este módulo no reimplementa reglas.
"""

from __future__ import annotations

from pydantic import Field

from ingestion.schemas.common import StrictModel
from rag_platform.domain.errors import DocumentTypeNotPermitted
from rag_platform.domain.models import ProjectConfiguration, ProjectDocumentType


class DocumentClassificationResult(StrictModel):
    """Resultado neutral de clasificar un documento para la plataforma.

    Attributes:
        document_type: ``code`` del tipo documental; debe existir en el catálogo
            del proyecto (validado por :func:`resolve_document_type`).
        topic: Tema principal detectado (texto libre del clasificador).
        document_type_confidence: Confianza del tipo en ``[0, 1]``.
        signals: Señales de evidencia que sustentan la decisión (trazabilidad).
        needs_review: ``True`` si la decisión es de baja confianza o conflictiva;
            obliga a decisión de elegibilidad antes de entrar a un snapshot.
    """

    document_type: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    document_type_confidence: float = Field(ge=0.0, le=1.0)
    signals: tuple[str, ...] = Field(default_factory=tuple)
    needs_review: bool = False


def resolve_document_type(
    configuration: ProjectConfiguration, code: str
) -> ProjectDocumentType:
    """Resuelve un ``document_type`` contra el catálogo versionado del proyecto.

    Args:
        configuration: Configuración (versionada) del proyecto propietario.
        code: ``code`` de tipo documental producido por la política de clasificación.

    Returns:
        El ``ProjectDocumentType`` del catálogo que coincide con ``code``.

    Raises:
        DocumentTypeNotPermitted: Si ningún tipo del catálogo tiene ese ``code``.
    """

    for document_type in configuration.document_types:
        if document_type.code == code:
            return document_type
    permitted = ", ".join(sorted(dt.code for dt in configuration.document_types))
    raise DocumentTypeNotPermitted(
        f"document_type {code!r} no está en el catálogo del proyecto (permitidos: {permitted})"
    )
