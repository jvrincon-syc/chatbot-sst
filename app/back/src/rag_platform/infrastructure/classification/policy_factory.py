"""Carga de la política de clasificación desde el snapshot de configuración (Fase 2).

Cierra la letra del plan (§Fase 2): la política SST se *carga desde el snapshot de
configuración* del proyecto en vez de fijarse en el llamador. El cargador vive en
infraestructura porque es quien puede conocer el adaptador concreto
(``SstClassificationPolicy``); la aplicación sigue dependiendo solo del puerto.

No reimplementa reglas: selecciona el adaptador que envuelve el motor SST legacy.
Selección fail-closed: si la configuración no permite derivar una política, lanza
``NoClassificationPolicyConfigured`` en vez de degradar a un clasificador por defecto.
"""

from __future__ import annotations

from rag_platform.application.classification_service import ClassificationPolicy
from rag_platform.domain.errors import NoClassificationPolicyConfigured
from rag_platform.domain.models import DocumentTypeTemplate, ProjectConfiguration
from rag_platform.infrastructure.classification.sst_policy import SstClassificationPolicy


def build_classification_policy(
    configuration: ProjectConfiguration,
) -> ClassificationPolicy:
    """Deriva la política de clasificación del snapshot de configuración del proyecto.

    Heurística de selección: si el catálogo del proyecto usa la taxonomía SST
    (algún ``ProjectDocumentType`` con plantilla ``SST``), la política es el
    adaptador SST que reproduce las decisiones legacy exactas.

    Args:
        configuration: Configuración versionada del proyecto (el snapshot).

    Returns:
        Una implementación de :class:`ClassificationPolicy`.

    Raises:
        NoClassificationPolicyConfigured: Si la configuración no resuelve política.

    Note:
        ponytail: selección por plantilla del catálogo; cuando existan varios
        motores por proyecto, sustituir por una clave de política explícita y
        versionada en ``ProjectConfiguration`` (requiere migración + ADR).
    """

    uses_sst_taxonomy = any(
        document_type.template is DocumentTypeTemplate.SST
        for document_type in configuration.document_types
    )
    if uses_sst_taxonomy:
        return SstClassificationPolicy()
    raise NoClassificationPolicyConfigured(
        "la configuración del proyecto no define una política de clasificación "
        "(no hay taxonomía con motor de reglas asociado)"
    )
