"""Fase 2: resolución de DocumentType contra catálogo + política SST congelada."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ingestion.classification.rules import classify_document
from ingestion.schemas.artifacts import DocumentControl
from ingestion.schemas.common import DocumentField
from rag_platform.application.classification_service import (
    ClassifyProjectDocumentUseCase,
)
from rag_platform.application.project_service import _TEMPLATE_DOCUMENT_TYPES
from rag_platform.domain.classification import (
    DocumentClassificationResult,
    resolve_document_type,
)
from rag_platform.domain.errors import (
    DocumentTypeNotPermitted,
    NoClassificationPolicyConfigured,
)
from rag_platform.domain.models import (
    CorpusOrganizationPolicy,
    DocumentTypeTemplate,
    ProjectConfiguration,
)
from rag_platform.infrastructure.classification.policy_factory import (
    build_classification_policy,
)
from rag_platform.infrastructure.classification.sst_policy import SstClassificationPolicy


def _config(template: DocumentTypeTemplate) -> ProjectConfiguration:
    return ProjectConfiguration(
        version=1,
        document_types=_TEMPLATE_DOCUMENT_TYPES[template],
        corpus_organization_policy=CorpusOrganizationPolicy.SST_LEGACY_V1,
        created_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )


# --- resolve_document_type (item 2): validación fail-closed contra catálogo ---


def test_resuelve_tipo_presente_en_catalogo_sst() -> None:
    resolved = resolve_document_type(_config(DocumentTypeTemplate.SST), "formulario")
    assert resolved.code == "formulario"


def test_rechaza_tipo_ausente_del_catalogo() -> None:
    # 'formulario' no existe en la plantilla GENERIC: fail-closed, no degrada.
    with pytest.raises(DocumentTypeNotPermitted):
        resolve_document_type(_config(DocumentTypeTemplate.GENERIC), "formulario")


# --- Adaptador SST (item 3): reproduce EXACTAMENTE las decisiones legacy -------


def test_adaptador_sst_reproduce_la_decision_legacy() -> None:
    policy = SstClassificationPolicy()
    result = policy.classify(
        source_relpath="sst/formularios/fr-sst-01.pdf",
        title="Formulario FR-SST inspección",
        document_code="FR-SST-01",
        page_texts=["Formato de inspección de seguridad"],
    )

    # La misma entrada por el motor legacy directo debe dar el mismo tipo/topic.
    control = DocumentControl(
        title=DocumentField(
            value="Formulario FR-SST inspección",
            value_raw="Formulario FR-SST inspección",
            status="extracted",
        ),
        code=DocumentField(value="FR-SST-01", value_raw="FR-SST-01", status="extracted"),
        version=DocumentField(value=None, status="not_found"),
        publication_date=DocumentField(value=None, status="not_found"),
        effective_date=DocumentField(value=None, status="not_found"),
    )
    legacy = classify_document(
        "sst/formularios/fr-sst-01.pdf",
        [{"text_raw": "Formato de inspección de seguridad"}],
        control,
    )
    assert isinstance(result, DocumentClassificationResult)
    assert result.document_type == legacy.document_type == "formulario"
    assert result.topic == legacy.topic


# --- Cargador de política desde el snapshot de configuración (item 3) ---------


def test_cargador_deriva_politica_sst_del_snapshot() -> None:
    policy = build_classification_policy(_config(DocumentTypeTemplate.SST))
    assert isinstance(policy, SstClassificationPolicy)


def test_cargador_falla_cerrado_sin_taxonomia_con_motor() -> None:
    # GENERIC no tiene motor de reglas asociado: no se degrada a un default.
    with pytest.raises(NoClassificationPolicyConfigured):
        build_classification_policy(_config(DocumentTypeTemplate.GENERIC))


# --- Caso de uso (composición item 2 + item 3) --------------------------------


def test_caso_de_uso_valida_clasificacion_sst_contra_catalogo() -> None:
    configuration = _config(DocumentTypeTemplate.SST)
    # La política se CARGA del snapshot de configuración, no se inyecta a mano.
    use_case = ClassifyProjectDocumentUseCase(
        policy=build_classification_policy(configuration)
    )
    result = use_case.execute(
        configuration=configuration,
        source_relpath="sst/manuales/manual-sst.pdf",
        title="Manual del Sistema de Gestión SST",
        page_texts=["Manual de seguridad y salud en el trabajo"],
    )
    assert result.document_type == "manual"  # tipo real presente en el catálogo SST


def test_caso_de_uso_falla_cerrado_si_tipo_no_esta_en_catalogo() -> None:
    # Proyecto con plantilla GENERIC pero documento clasificado como 'manual'
    # por el motor SST: si 'manual' sí está en GENERIC, usamos un doc que da otro
    # tipo ausente. 'politica' no está en GENERIC.
    use_case = ClassifyProjectDocumentUseCase(policy=SstClassificationPolicy())
    with pytest.raises(DocumentTypeNotPermitted):
        use_case.execute(
            configuration=_config(DocumentTypeTemplate.GENERIC),
            source_relpath="sst/politicas/politica-sst.pdf",
            title="Política de seguridad y salud",
            page_texts=["Política de seguridad y salud en el trabajo"],
        )
