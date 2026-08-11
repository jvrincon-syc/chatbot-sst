"""Adaptador SST de ``ClassificationPolicy`` (Fase 2, enfoque aditivo mínimo).

Envuelve el motor de reglas SST existente (``ingestion.classification.rules``)
y traduce su ``Classification`` al resultado neutral de plataforma. **No
reimplementa reglas**: reproduce exactamente las decisiones SST actuales, de modo
que ``sst-general`` conserva su comportamiento mientras la validación de política
(catálogo del proyecto) se aplica en la capa de aplicación.

Vive en infraestructura porque acopla al motor concreto SST; la aplicación solo
conoce el puerto ``ClassificationPolicy``.
"""

from __future__ import annotations

from typing import Sequence

from ingestion.classification.rules import classify_document
from ingestion.schemas.artifacts import DocumentControl
from ingestion.schemas.common import DocumentField
from rag_platform.domain.classification import DocumentClassificationResult

#: Señales del clasificador legacy que marcan una decisión de baja confianza.
_LOW_CONFIDENCE_WARNING = "route_only_low_confidence"


class SstClassificationPolicy:
    """Política de clasificación que reproduce las decisiones SST legacy."""

    def classify(
        self,
        *,
        source_relpath: str,
        title: str,
        document_code: str,
        page_texts: Sequence[str],
    ) -> DocumentClassificationResult:
        """Delega en ``classify_document`` y mapea a un resultado de plataforma.

        ``needs_review`` se deriva de las mismas señales que el pipeline legacy
        trata como ambiguas (conflicto o evidencia solo-por-ruta); el umbral
        numérico de confianza permanece en el pipeline legacy, no se duplica aquí.
        """

        control = DocumentControl(
            title=_field(title),
            code=_field(document_code),
            version=_not_found(),
            publication_date=_not_found(),
            effective_date=_not_found(),
        )
        pages = [{"text_raw": text} for text in page_texts]
        classification = classify_document(source_relpath, pages, control)
        needs_review = bool(classification.conflicts) or (
            _LOW_CONFIDENCE_WARNING in classification.warnings
        )
        return DocumentClassificationResult(
            document_type=classification.document_type,
            topic=classification.topic,
            document_type_confidence=classification.document_type_confidence.value or 0.0,
            signals=tuple(classification.signals),
            needs_review=needs_review,
        )


def _field(value: str) -> DocumentField:
    """Construye un ``DocumentField`` extraído o ``not_found`` según haya texto."""

    if value:
        return DocumentField(value=value, value_raw=value, status="extracted")
    return _not_found()


def _not_found() -> DocumentField:
    return DocumentField(value=None, status="not_found")
