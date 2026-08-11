"""Política de clasificación documental de plataforma (Fase 2).

Define el puerto ``ClassificationPolicy`` y el caso de uso que **compone** dos
piezas del plan (§Fase 2, política documental):

1. clasificar el documento con una política cargada por proyecto (el adaptador
   SST vive en infraestructura y reproduce las decisiones legacy exactas);
2. resolver el ``document_type`` resultante contra el catálogo versionado del
   proyecto de forma fail-closed.

La capa de aplicación no importa el motor de reglas SST: recibe la política por
inyección, de modo que otro proyecto puede aportar su propia política sin tocar
este código (dependencias por constructor, sin service locator).
"""

from __future__ import annotations

from typing import Protocol, Sequence

from rag_platform.domain.classification import (
    DocumentClassificationResult,
    resolve_document_type,
)
from rag_platform.domain.models import ProjectConfiguration


class ClassificationPolicy(Protocol):
    """Puerto: clasifica un documento en un resultado neutral de plataforma.

    Las implementaciones (p. ej. el adaptador SST) traducen desde su motor
    concreto sin filtrar tipos SDK ni el ``Literal`` legacy hacia la aplicación.
    """

    def classify(
        self,
        *,
        source_relpath: str,
        title: str,
        document_code: str,
        page_texts: Sequence[str],
    ) -> DocumentClassificationResult:
        """Clasifica desde la evidencia documental más fuerte disponible."""
        ...


class ClassifyProjectDocumentUseCase:
    """Clasifica un documento y valida su tipo contra el catálogo del proyecto.

    Es fail-closed: si la política produce un ``document_type`` que el catálogo
    versionado del proyecto no declara, ``resolve_document_type`` lanza
    ``DocumentTypeNotPermitted`` y el documento no se degrada a la ruta legacy.
    """

    def __init__(self, *, policy: ClassificationPolicy) -> None:
        self._policy = policy

    def execute(
        self,
        *,
        configuration: ProjectConfiguration,
        source_relpath: str,
        title: str = "",
        document_code: str = "",
        page_texts: Sequence[str] = (),
    ) -> DocumentClassificationResult:
        """Clasifica y valida contra el catálogo; devuelve el resultado validado.

        Args:
            configuration: Configuración versionada del proyecto propietario.
            source_relpath: Localizador versionado del documento (evidencia débil).
            title: Título del control documental, si se conoce.
            document_code: Código del control documental, si se conoce.
            page_texts: Textos de página como evidencia de contenido.

        Returns:
            El ``DocumentClassificationResult`` cuyo ``document_type`` ya existe
            en el catálogo del proyecto.

        Raises:
            DocumentTypeNotPermitted: Si el tipo clasificado no está en el catálogo.
        """

        result = self._policy.classify(
            source_relpath=source_relpath,
            title=title,
            document_code=document_code,
            page_texts=page_texts,
        )
        resolve_document_type(configuration, result.document_type)
        return result
