from __future__ import annotations

import pytest
from pydantic import ValidationError

from ingestion.schemas.artifacts import (
    Classification,
    DocumentControl,
    FormControl,
    FormGroup,
    FormLabel,
    FormsArtifact,
    MetadataArtifact,
    OcrArtifact,
    OcrPage,
    OcrWord,
    PageRecord,
    PagesArtifact,
    TableCell,
    TableRecord,
    TablesArtifact,
)
from ingestion.schemas.common import (
    BBox,
    ConfidenceMetric,
    DocumentField,
    Evidence,
    MeasuredValue,
    NormalizationAction,
    Observation,
    PageBlock,
    RemovedSpan,
)
from ingestion.schemas.inventory import InventoryRecord


def unavailable_confidence() -> ConfidenceMetric:
    return ConfidenceMetric(kind="unavailable", value=None)


def not_evaluated() -> Observation:
    return Observation(status="not_evaluated", value=None)


def test_canonical_artifacts_require_literal_schema_version_and_forbid_extras() -> None:
    with pytest.raises(ValidationError):
        PagesArtifact(document_id="doc_1", page_count=0, pages=[])

    with pytest.raises(ValidationError):
        PagesArtifact(
            schema_version="1.0",
            document_id="doc_1",
            page_count=0,
            pages=[],
        )

    with pytest.raises(ValidationError):
        PagesArtifact(
            schema_version="2.0",
            document_id="doc_1",
            page_count=0,
            pages=[],
            invented=True,
        )


@pytest.mark.parametrize(
    "path",
    [
        "/absolute/file.pdf",
        "C:/absolute/file.pdf",
        r"C:\absolute\file.pdf",
        "./file.pdf",
        "../file.pdf",
        "folder/../file.pdf",
        "folder/./file.pdf",
        r"folder\file.pdf",
    ],
)
def test_inventory_rejects_nonportable_canonical_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        InventoryRecord(
            schema_version="2.0",
            document_id="doc_1",
            source_relpath=path,
            document_name="file.pdf",
            detected_extension=".pdf",
            reported_extension=".pdf",
            mime_type="application/pdf",
            content_hash="abc",
            file_size=1,
            ingestion_date="2026-07-17T00:00:00Z",
            category_inferred="manuales",
            processing_status="pending",
            pipeline_version="2.0.0",
            corpus_version="2",
        )


def test_bbox_requires_positive_area() -> None:
    box = BBox(
        x0=10,
        top=20,
        x1=30,
        bottom=40,
        coordinate_system="pdf_points",
    )
    assert box.x1 > box.x0

    with pytest.raises(ValidationError):
        BBox(
            x0=10,
            top=20,
            x1=10,
            bottom=40,
            coordinate_system="pdf_points",
        )


def test_evidence_preserves_geometry_provenance_and_warnings() -> None:
    evidence = Evidence(
        page_number=2,
        bbox=BBox(
            x0=1,
            top=2,
            x1=3,
            bottom=4,
            coordinate_system="pdf_points",
        ),
        region="header",
        text="Versión 3",
        pattern=r"Versión\s+3",
        source="visual_text",
        warnings=["ocr_character_uncertain"],
    )
    assert evidence.region == "header"
    assert evidence.bbox is not None


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "detected", "value": True},
        {"status": "detected", "value": False, "evidence": [{"text": "legacy"}]},
        {"status": "not_detected", "value": False},
        {"status": "not_detected", "value": True, "engine": "layout"},
        {"status": "not_evaluated", "value": False},
        {"status": "not_evaluated", "value": True},
    ],
)
def test_observation_rejects_invalid_status_value_provenance_combinations(
    payload: dict,
) -> None:
    with pytest.raises(ValidationError):
        Observation(**payload)


def test_observation_accepts_only_valid_tristate_combinations() -> None:
    detected = Observation(
        status="detected",
        value=True,
        evidence=[Evidence(page_number=1, text="Visible checkbox")],
    )
    absent = Observation(
        status="not_detected",
        value=False,
        engine="layout-detector",
    )
    unknown = Observation(status="not_evaluated", value=None)

    assert detected.value is True
    assert absent.value is False
    assert unknown.value is None


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "measured", "value": 0.8},
        {
            "kind": "measured",
            "value": 0.8,
            "engine": "tesseract",
            "engine_version": "5",
            "unit": "mean_word_confidence",
            "sample_size": 0,
        },
        {"kind": "estimated", "value": 0.8},
        {"kind": "unavailable", "value": 0.8},
        {"kind": "estimated", "value": 1.1, "method": "proxy"},
    ],
)
def test_confidence_metric_rejects_invalid_provenance(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ConfidenceMetric(**payload)


def test_confidence_metric_distinguishes_measured_estimated_and_unavailable() -> None:
    measured = ConfidenceMetric(
        kind="measured",
        value=0.87,
        engine="tesseract",
        engine_version="5.5",
        unit="mean_word_confidence",
        sample_size=23,
    )
    estimated = ConfidenceMetric(
        kind="estimated",
        value=0.7,
        method="legacy_sidecar_proxy",
    )
    unavailable = unavailable_confidence()

    assert measured.sample_size == 23
    assert estimated.method == "legacy_sidecar_proxy"
    assert unavailable.value is None


def test_measured_value_keeps_numeric_rotation_separate_from_observations() -> None:
    rotation = MeasuredValue(
        status="estimated",
        value=90,
        unit="degrees",
        method="legacy_assertion",
    )
    assert rotation.value == 90
    assert not isinstance(rotation.value, bool)

    with pytest.raises(ValidationError):
        MeasuredValue(
            status="unavailable",
            value=0,
            unit="degrees",
        )


def test_page_artifact_preserves_text_layout_removals_actions_and_typed_confidence() -> None:
    box = BBox(
        x0=10,
        top=10,
        x1=100,
        bottom=30,
        coordinate_system="pdf_points",
    )
    page = PageRecord(
        page_number=1,
        text_raw="CONFIDENCIAL\nTexto corri-\ndo",
        text_normalized="Texto corrido",
        extraction_method="hybrid",
        blocks=[
            PageBlock(
                block_id="b1",
                text="Texto corri-",
                bbox=box,
                extraction_method="pdf_digital",
                role="body",
            )
        ],
        removed_spans=[
            RemovedSpan(
                text="CONFIDENCIAL",
                reason="repeated_header",
                bbox=box,
            )
        ],
        normalization_actions=[
            NormalizationAction(
                action="join_hyphenated_word",
                before="corri-\ndo",
                after="corrido",
            )
        ],
        ocr_confidence=unavailable_confidence(),
        warnings=["regional_ocr_unavailable"],
    )
    artifact = PagesArtifact(
        schema_version="2.0",
        document_id="doc_1",
        page_count=1,
        pages=[page],
    )
    assert artifact.pages[0].extraction_method == "hybrid"
    assert artifact.pages[0].text_raw.startswith("CONFIDENCIAL")
    assert artifact.pages[0].ocr_confidence.kind == "unavailable"


def test_ocr_artifact_preserves_words_geometry_page_and_document_metrics() -> None:
    box = BBox(
        x0=1,
        top=2,
        x1=20,
        bottom=12,
        coordinate_system="pixels",
    )
    measured = ConfidenceMetric(
        kind="measured",
        value=0.9,
        engine="tesseract",
        engine_version="5.5",
        unit="mean_word_confidence",
        sample_size=1,
    )
    artifact = OcrArtifact(
        schema_version="2.0",
        document_id="doc_1",
        engine="tesseract",
        engine_version="5.5",
        language="spa",
        document_confidence=measured,
        pages=[
            OcrPage(
                page_number=1,
                words=[OcrWord(text="Texto", bbox=box, confidence=0.9)],
                confidence=measured,
                word_count=1,
                low_confidence_word_count=0,
                deskew=not_evaluated(),
                rotation=MeasuredValue(
                    status="measured",
                    value=0,
                    unit="degrees",
                    engine="tesseract",
                    engine_version="5.5",
                ),
                handwriting=not_evaluated(),
            )
        ],
    )
    assert artifact.pages[0].words[0].bbox.coordinate_system == "pixels"
    assert artifact.document_confidence.kind == "measured"


def test_table_artifact_preserves_geometry_cells_spans_representation_and_quality() -> None:
    box = BBox(
        x0=1,
        top=2,
        x1=100,
        bottom=60,
        coordinate_system="pdf_points",
    )
    artifact = TablesArtifact(
        schema_version="2.0",
        document_id="doc_1",
        table_count=1,
        tables=[
            TableRecord(
                table_id="table_1",
                page_number=1,
                bbox=box,
                cells=[
                    TableCell(
                        row_index=0,
                        column_index=0,
                        row_span=1,
                        column_span=2,
                        text="AUMENTAN",
                        bbox=box,
                    )
                ],
                markdown_representation="| AUMENTAN |",
                extractor="pdfplumber",
                quality=ConfidenceMetric(
                    kind="estimated",
                    value=0.8,
                    method="geometry_coverage",
                ),
            )
        ],
        page_observations=[
            Observation(
                status="detected",
                value=True,
                method="pdfplumber",
                evidence=[Evidence(page_number=1, bbox=box)],
            )
        ],
    )
    assert artifact.tables[0].cells[0].column_span == 2


def test_forms_artifact_preserves_label_control_and_blank_area_associations() -> None:
    label_box = BBox(
        x0=1,
        top=2,
        x1=30,
        bottom=12,
        coordinate_system="pdf_points",
    )
    control_box = BBox(
        x0=31,
        top=2,
        x1=90,
        bottom=12,
        coordinate_system="pdf_points",
    )
    artifact = FormsArtifact(
        schema_version="2.0",
        document_id="doc_1",
        groups=[
            FormGroup(
                group_id="complaint",
                page_number=1,
                labels=[FormLabel(label_id="name", text="Nombre", bbox=label_box)],
                controls=[
                    FormControl(
                        control_id="name_blank",
                        control_type="blank_area",
                        bbox=control_box,
                        label_id="name",
                    ),
                    FormControl(
                        control_id="anonymous",
                        control_type="selection",
                        bbox=control_box,
                        label_id="name",
                        selected=False,
                    ),
                ],
            )
        ],
        page_observations=[
            Observation(
                status="detected",
                value=True,
                method="vector_geometry",
                evidence=[Evidence(page_number=1, bbox=control_box)],
            )
        ],
    )
    assert artifact.groups[0].controls[0].label_id == "name"
    assert artifact.groups[0].controls[0].control_type == "blank_area"


def test_metadata_keeps_control_classification_features_reviews_and_portable_paths() -> None:
    artifact = MetadataArtifact(
        schema_version="2.0",
        document_id="doc_1",
        document_name="policy.pdf",
        source_relpath="policies/policy.pdf",
        normalized_relpath="policies/policy.md",
        document_control=DocumentControl(
            title=DocumentField(
                value="Política SST",
                value_raw="POLÍTICA SST",
                status="extracted",
                evidence=[Evidence(page_number=1, source="visual_text")],
            ),
            code=DocumentField(value=None, status="not_evaluated"),
            version=DocumentField(value=None, status="not_evaluated"),
            publication_date=DocumentField(value=None, status="not_found"),
            effective_date=DocumentField(value=None, status="not_evaluated"),
        ),
        classification=Classification(
            document_type="politica",
            document_type_confidence=ConfidenceMetric(
                kind="estimated",
                value=0.95,
                method="title_signal_scoring",
            ),
            topic="SST",
            topic_confidence=ConfidenceMetric(
                kind="estimated",
                value=0.7,
                method="content_signal_scoring",
            ),
            signals=["explicit_title:politica"],
            route_prior="policies",
            content_prediction="politica",
            conflict_status="none",
        ),
        page_count=1,
        language="es",
        extraction_method="hybrid",
        ocr_confidence=unavailable_confidence(),
        handwriting=not_evaluated(),
        tables=not_evaluated(),
        forms=not_evaluated(),
        source_hash="abc",
        corpus_version="2",
        pipeline_version="2.0.0",
        processing_status="needs_review",
        review_reasons=["regional_ocr_unavailable"],
    )
    assert artifact.document_control.title.value == "Política SST"
    assert artifact.classification.document_type_confidence.value == 0.95
    assert artifact.source_relpath == "policies/policy.pdf"


def test_document_field_preserves_raw_value_status_evidence_and_warnings() -> None:
    field = DocumentField(
        value="RG-SST-01",
        value_raw="RG.SST-01",
        status="conflicting",
        evidence=[Evidence(page_number=1), Evidence(page_number=2)],
        warnings=["header_values_disagree"],
    )
    assert field.value_raw == "RG.SST-01"
    assert len(field.evidence) == 2


def test_inventory_is_schema_2_source_relative_and_excludes_skipped_status() -> None:
    record = InventoryRecord(
        schema_version="2.0",
        document_id="doc_1",
        source_relpath="manuales/file.pdf",
        document_name="file.pdf",
        detected_extension=".pdf",
        reported_extension=".pdf",
        mime_type="application/pdf",
        content_hash="abc",
        file_size=1,
        ingestion_date="2026-07-17T00:00:00Z",
        category_inferred="manuales",
        processing_status="processed",
        pipeline_version="2.0.0",
        corpus_version="2",
    )
    assert record.source_relpath == "manuales/file.pdf"

    with pytest.raises(ValidationError):
        InventoryRecord(**{**record.model_dump(), "processing_status": "skipped"})
