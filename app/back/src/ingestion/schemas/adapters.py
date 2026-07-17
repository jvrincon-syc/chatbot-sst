from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping, Optional

from ingestion.schemas.artifacts import (
    Classification,
    DocumentControl,
    MetadataArtifact,
    OcrArtifact,
    OcrPage,
    PageRecord,
    PagesArtifact,
    TableRecord,
    TablesArtifact,
)
from ingestion.schemas.common import (
    ConfidenceMetric,
    DocumentField,
    Evidence,
    MeasuredValue,
    Observation,
)
from ingestion.schemas.inventory import InventoryRecord
from ingestion.schemas.legacy_v1 import (
    LegacyInventoryRecord,
    LegacyMetadataArtifact,
    LegacyOcrArtifact,
    LegacyPagesArtifact,
    LegacyTablesArtifact,
)


_HISTORIC_DOCUMENT_TYPES = {
    "manual",
    "formulario",
    "politica",
    "reglamento",
    "programa",
    "matriz",
    "procedimiento",
    "anexo",
    "instructivo",
    "capacitacion",
    "acta",
    "norma",
    "guia",
    "informacion_general",
    "otro",
}


def _unavailable_confidence() -> ConfidenceMetric:
    return ConfidenceMetric(kind="unavailable", value=None)


def _legacy_confidence(value: Optional[float], label: str) -> ConfidenceMetric:
    if value is None:
        return _unavailable_confidence()
    return ConfidenceMetric(
        kind="estimated",
        value=value,
        method="legacy_assertion",
        provenance=label,
        warnings=["legacy_confidence_not_measured"],
    )


def _legacy_feature(value: Optional[bool], feature: str) -> Observation:
    if value is not True:
        return Observation(status="not_evaluated", value=None)
    return Observation(
        status="detected",
        value=True,
        method="legacy_assertion",
        evidence=[
            Evidence(
                text=f"Legacy schema 1.0 asserted {feature}=true",
                source="legacy_v1",
            )
        ],
        warnings=["legacy_detection_unverified"],
    )


def _legacy_document_field(value: Any, field_name: str) -> DocumentField:
    if value is None:
        return DocumentField(value=None, status="not_evaluated")
    return DocumentField(
        value=value,
        value_raw=value,
        status="extracted",
        evidence=[
            Evidence(
                text=f"Legacy schema 1.0 field {field_name}",
                source="legacy_v1",
            )
        ],
        warnings=["legacy_field_provenance_limited"],
    )


def _path_flavour(value: str):
    if PureWindowsPath(value).is_absolute():
        return PureWindowsPath
    return PurePosixPath


def _is_absolute(value: str) -> bool:
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute()


def _safe_basename(value: str, fallback: str) -> str:
    path_type = _path_flavour(value)
    name = path_type(value).name or fallback
    if name in {".", ".."} or "/" in name or "\\" in name:
        return fallback
    return name


def _adapt_path(
    value: str,
    root: Any,
    document_id: str,
    fallback_name: str,
) -> tuple[str, Optional[str], list[str]]:
    if not _is_absolute(value):
        normalized = value.replace("\\", "/")
        parts = normalized.split("/")
        if normalized and all(part not in {"", ".", ".."} for part in parts):
            return normalized, None, []
    elif root is not None:
        path_type = _path_flavour(value)
        try:
            relative = path_type(value).relative_to(path_type(str(root))).as_posix()
        except ValueError:
            pass
        else:
            return relative, None, []

    basename = _safe_basename(value, fallback_name)
    placeholder = f"legacy/{document_id}/{basename}"
    return placeholder, value, ["legacy_absolute_path_not_relativized"]


def _adapt_metadata(
    payload: Mapping[str, Any], context: Mapping[str, Any]
) -> MetadataArtifact:
    legacy = LegacyMetadataArtifact.model_validate(payload)
    source_relpath, source_legacy_path, source_warnings = _adapt_path(
        legacy.source_path,
        context.get("raw_root"),
        legacy.document_id,
        legacy.document_name,
    )
    normalized_relpath, normalized_legacy_path, normalized_warnings = _adapt_path(
        legacy.normalized_path,
        context.get("normalized_root"),
        legacy.document_id,
        f"{legacy.document_id}.md",
    )
    warnings = list(
        dict.fromkeys(
            [
                *legacy.warnings,
                *source_warnings,
                *normalized_warnings,
            ]
        )
    )
    legacy_path = source_legacy_path or normalized_legacy_path
    processing_status = legacy.processing_status
    review_reasons: list[str] = []
    if processing_status == "skipped":
        processing_status = "needs_review"
        warning = "legacy_skipped_status_mapped_to_needs_review"
        warnings.append(warning)
        review_reasons.append(warning)

    classification_confidence = _legacy_confidence(
        legacy.classification_confidence,
        "legacy_classification_confidence",
    )
    document_type = (
        legacy.document_type
        if legacy.document_type in _HISTORIC_DOCUMENT_TYPES
        else "otro"
    )
    if document_type != legacy.document_type:
        warnings.append("legacy_document_type_mapped_to_otro")

    return MetadataArtifact(
        schema_version="2.0",
        document_id=legacy.document_id,
        document_name=legacy.document_name,
        source_relpath=source_relpath,
        normalized_relpath=normalized_relpath,
        legacy_path=legacy_path,
        document_control=DocumentControl(
            title=DocumentField(value=None, status="not_evaluated"),
            code=DocumentField(value=None, status="not_evaluated"),
            version=_legacy_document_field(legacy.version, "version"),
            publication_date=_legacy_document_field(
                legacy.publication_date, "publication_date"
            ),
            effective_date=_legacy_document_field(
                legacy.effective_date, "effective_date"
            ),
        ),
        classification=Classification(
            document_type=document_type,
            document_type_confidence=classification_confidence,
            topic=legacy.topic,
            topic_confidence=classification_confidence.model_copy(deep=True),
            signals=["legacy_v1_classification"],
            route_prior=None,
            content_prediction=None,
            conflict_status="none",
            warnings=["legacy_classification_provenance_limited"],
        ),
        page_count=legacy.page_count,
        language=legacy.language,
        extraction_method=legacy.extraction_method,
        ocr_confidence=_legacy_confidence(
            legacy.ocr_confidence, "legacy_metadata_ocr_confidence"
        ),
        handwriting=_legacy_feature(
            legacy.contains_handwriting, "contains_handwriting"
        ),
        tables=_legacy_feature(legacy.contains_tables, "contains_tables"),
        forms=Observation(status="not_evaluated", value=None),
        source_hash=legacy.content_hash,
        corpus_version=legacy.corpus_version,
        pipeline_version=legacy.pipeline_version,
        processing_status=processing_status,
        review_reasons=review_reasons,
        warnings=list(dict.fromkeys(warnings)),
        **({"processed_at": legacy.processed_at} if legacy.processed_at else {}),
    )


def _adapt_pages(payload: Mapping[str, Any]) -> PagesArtifact:
    legacy = LegacyPagesArtifact.model_validate(payload)
    pages = []
    for page in legacy.pages:
        warnings = list(page.warnings)
        if page.has_handwriting_warning:
            warnings.append("legacy_handwriting_warning_unverified")
        pages.append(
            PageRecord(
                page_number=page.page_number,
                text_raw=page.text_raw,
                text_normalized=page.text_normalized,
                extraction_method=page.extraction_method,
                ocr_confidence=_legacy_confidence(
                    page.ocr_confidence, "legacy_page_ocr_confidence"
                ),
                warnings=warnings,
            )
        )
    return PagesArtifact(
        schema_version="2.0",
        document_id=legacy.document_id,
        page_count=legacy.page_count,
        pages=pages,
    )


def _adapt_ocr(payload: Mapping[str, Any]) -> OcrArtifact:
    legacy = LegacyOcrArtifact.model_validate(payload)
    pages = []
    for page in legacy.pages:
        if page.rotation_detected_degrees is None:
            rotation = MeasuredValue(status="unavailable", value=None)
        else:
            rotation = MeasuredValue(
                status="estimated",
                value=page.rotation_detected_degrees,
                unit="degrees",
                method="legacy_assertion",
                warnings=["legacy_rotation_not_measured"],
            )
        pages.append(
            OcrPage(
                page_number=page.page_number,
                confidence=_legacy_confidence(
                    page.confidence, "legacy_page_ocr_confidence"
                ),
                word_count=page.word_count,
                low_confidence_word_count=page.low_confidence_word_count,
                deskew=_legacy_feature(page.deskew_applied, "deskew_applied"),
                rotation=rotation,
                handwriting=_legacy_feature(
                    page.contains_handwriting, "contains_handwriting"
                ),
                warnings=page.warnings,
            )
        )
    return OcrArtifact(
        schema_version="2.0",
        document_id=legacy.document_id,
        engine=legacy.engine,
        engine_version=legacy.engine_version,
        language=legacy.language,
        document_confidence=_legacy_confidence(
            legacy.overall_confidence, "legacy_document_ocr_confidence"
        ),
        pages=pages,
    )


def _adapt_tables(payload: Mapping[str, Any]) -> TablesArtifact:
    legacy = LegacyTablesArtifact.model_validate(payload)
    tables = [
        TableRecord(
            table_id=table.table_id,
            page_number=table.page_number,
            bbox=None,
            caption=table.caption,
            headers=table.headers,
            rows=table.rows,
            markdown_representation=table.markdown_representation,
            extractor="legacy_v1",
            quality=_legacy_confidence(table.quality, "legacy_table_quality"),
            warnings=[*table.warnings, "legacy_geometry_unavailable"],
        )
        for table in legacy.tables
    ]
    page_observations = []
    for table in legacy.tables:
        page_observations.append(
            Observation(
                status="detected",
                value=True,
                method="legacy_assertion",
                evidence=[
                    Evidence(
                        page_number=table.page_number,
                        text=f"Legacy table assertion {table.table_id}",
                        source="legacy_v1",
                    )
                ],
                warnings=["legacy_detection_unverified"],
            )
        )
    return TablesArtifact(
        schema_version="2.0",
        document_id=legacy.document_id,
        table_count=legacy.table_count,
        tables=tables,
        page_observations=page_observations,
    )


def _adapt_inventory(
    payload: Mapping[str, Any], context: Mapping[str, Any]
) -> InventoryRecord:
    legacy = LegacyInventoryRecord.model_validate(payload)
    source_relpath, legacy_path, warnings = _adapt_path(
        legacy.source_path,
        context.get("raw_root"),
        legacy.document_id,
        legacy.document_name,
    )
    processing_status = legacy.processing_status
    if processing_status == "skipped":
        processing_status = "needs_review"
        warnings.append("legacy_skipped_status_mapped_to_needs_review")
    return InventoryRecord(
        schema_version="2.0",
        document_id=legacy.document_id,
        source_relpath=source_relpath,
        legacy_path=legacy_path,
        document_name=legacy.document_name,
        detected_extension=legacy.detected_extension,
        reported_extension=legacy.reported_extension,
        mime_type=legacy.mime_type,
        content_hash=legacy.content_hash,
        file_size=legacy.file_size,
        ingestion_date=legacy.ingestion_date,
        category_inferred=legacy.category_inferred,
        document_version=legacy.document_version,
        page_count=legacy.page_count,
        processing_status=processing_status,
        pipeline_version=legacy.pipeline_version,
        corpus_version=legacy.corpus_version,
        warnings=warnings,
    )


def adapt_v1_to_v2(
    payload: Mapping[str, Any],
    artifact_type: str,
    context: Optional[Mapping[str, Any]] = None,
):
    """Validate an explicit 1.0 payload and return its canonical 2.0 model."""

    context = context or {}
    normalized_type = artifact_type.lower().removesuffix("artifact")
    if normalized_type == "metadata":
        return _adapt_metadata(payload, context)
    if normalized_type == "pages":
        return _adapt_pages(payload)
    if normalized_type == "ocr":
        return _adapt_ocr(payload)
    if normalized_type == "tables":
        return _adapt_tables(payload)
    if normalized_type in {"inventory", "inventoryrecord"}:
        return _adapt_inventory(payload, context)
    if normalized_type == "forms":
        raise ValueError("schema 1.0 did not define a forms artifact")
    raise ValueError(f"unknown artifact_type: {artifact_type!r}")
