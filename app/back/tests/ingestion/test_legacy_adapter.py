from __future__ import annotations

from pathlib import Path, PureWindowsPath

import pytest
from pydantic import ValidationError

from ingestion.schemas.adapters import adapt_v1_to_v2
from ingestion.schemas.artifacts import MetadataArtifact, OcrArtifact
from ingestion.schemas.loader import load_artifact


def legacy_metadata(**overrides: object) -> dict:
    payload = {
        "schema_version": "1.0",
        "document_id": "doc_legacy",
        "document_name": "policy.pdf",
        "source_path": "policies/policy.pdf",
        "normalized_path": "policies/policy.md",
        "document_type": "politica",
        "topic": "SST",
        "subtopic": None,
        "version": None,
        "publication_date": None,
        "effective_date": None,
        "page_count": 1,
        "language": "es",
        "extraction_method": "ocr",
        "ocr_engine": "tesseract",
        "ocr_confidence": 0.73,
        "contains_handwriting": False,
        "contains_tables": False,
        "classification_confidence": 0.9,
        "content_hash": "abc",
        "corpus_version": "1",
        "pipeline_version": "1.0.0",
        "processing_status": "processed",
        "warnings": [],
        "processed_at": "2026-07-16T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def legacy_ocr(confidence: float = 0.73) -> dict:
    return {
        "schema_version": "1.0",
        "document_id": "doc_legacy",
        "engine": "tesseract",
        "engine_version": "5.5",
        "language": "spa",
        "overall_confidence": confidence,
        "pages": [
            {
                "page_number": 1,
                "confidence": confidence,
                "word_count": 10,
                "low_confidence_word_count": 0,
                "deskew_applied": False,
                "rotation_detected_degrees": 0,
                "contains_handwriting": False,
                "warnings": [],
            }
        ],
    }


@pytest.mark.parametrize("version", [None, "3.0", "", 2])
def test_loader_fails_closed_for_missing_or_unknown_version(version: object) -> None:
    payload = legacy_metadata()
    if version is None:
        payload.pop("schema_version")
    else:
        payload["schema_version"] = version

    with pytest.raises(ValueError, match="schema_version"):
        load_artifact(payload, "metadata", {})


def test_loader_dispatches_explicit_v1_through_adapter_and_v2_directly() -> None:
    adapted = load_artifact(legacy_metadata(), "metadata", {})
    assert isinstance(adapted, MetadataArtifact)
    assert adapted.schema_version == "2.0"

    direct = load_artifact(adapted.model_dump(mode="json"), "metadata", {})
    assert isinstance(direct, MetadataArtifact)
    assert direct == adapted


@pytest.mark.parametrize("confidence", [0.0, 0.42, 1.0])
def test_every_legacy_ocr_confidence_is_estimated(confidence: float) -> None:
    artifact = load_artifact(legacy_ocr(confidence), "ocr", {})
    assert isinstance(artifact, OcrArtifact)
    assert artifact.document_confidence.kind == "estimated"
    assert artifact.document_confidence.value == confidence
    assert artifact.pages[0].confidence.kind == "estimated"
    assert artifact.pages[0].confidence.value == confidence


@pytest.mark.parametrize(
    ("payload", "artifact_type"),
    [
        (legacy_metadata(ocr_confidence=True), "metadata"),
        (legacy_metadata(classification_confidence=False), "metadata"),
        (legacy_ocr(True), "ocr"),
    ],
)
def test_legacy_boolean_confidence_is_rejected_before_float_coercion(
    payload: dict,
    artifact_type: str,
) -> None:
    with pytest.raises(ValidationError):
        load_artifact(payload, artifact_type, {})


def test_legacy_false_or_missing_features_are_not_evaluated() -> None:
    false_features = adapt_v1_to_v2(legacy_metadata(), "metadata", {})
    missing_features_payload = legacy_metadata()
    missing_features_payload.pop("contains_handwriting")
    missing_features_payload.pop("contains_tables")
    missing_features = adapt_v1_to_v2(missing_features_payload, "metadata", {})

    assert false_features.handwriting.status == "not_evaluated"
    assert false_features.handwriting.value is None
    assert false_features.tables.status == "not_evaluated"
    assert missing_features.handwriting.status == "not_evaluated"
    assert missing_features.tables.status == "not_evaluated"


def test_legacy_true_feature_becomes_warned_detection_with_evidence() -> None:
    adapted = adapt_v1_to_v2(
        legacy_metadata(contains_handwriting=True, contains_tables=True),
        "metadata",
        {},
    )

    for feature in (adapted.handwriting, adapted.tables):
        assert feature.status == "detected"
        assert feature.value is True
        assert feature.method == "legacy_assertion"
        assert feature.evidence
        assert "legacy_detection_unverified" in feature.warnings


def test_legacy_null_document_control_without_provenance_is_not_evaluated() -> None:
    adapted = adapt_v1_to_v2(legacy_metadata(), "metadata", {})
    assert adapted.document_control.version.status == "not_evaluated"
    assert adapted.document_control.publication_date.status == "not_evaluated"
    assert adapted.document_control.effective_date.status == "not_evaluated"


def test_absolute_legacy_path_under_known_root_is_relativized() -> None:
    raw_root = PureWindowsPath("C:/known/raw")
    normalized_root = PureWindowsPath("C:/known/normalized")
    source = raw_root / "policies" / "policy.pdf"
    normalized = normalized_root / "policies" / "policy.md"
    adapted = adapt_v1_to_v2(
        legacy_metadata(
            source_path=str(source),
            normalized_path=str(normalized),
        ),
        "metadata",
        {"raw_root": raw_root, "normalized_root": normalized_root},
    )

    assert adapted.source_relpath == "policies/policy.pdf"
    assert adapted.normalized_relpath == "policies/policy.md"
    assert adapted.legacy_path is None


def test_unknown_absolute_legacy_path_is_preserved_only_as_legacy_path() -> None:
    outside = PureWindowsPath("D:/outside/policy.pdf")
    adapted = adapt_v1_to_v2(
        legacy_metadata(source_path=str(outside)),
        "metadata",
        {"raw_root": PureWindowsPath("C:/known/raw")},
    )

    assert adapted.source_relpath == "legacy/doc_legacy/policy.pdf"
    assert adapted.legacy_path == str(outside)
    assert not Path(adapted.source_relpath).is_absolute()
    assert "legacy_absolute_path_not_relativized" in adapted.warnings


def test_both_unknown_absolute_metadata_paths_are_preserved_explicitly() -> None:
    source = str(PureWindowsPath("D:/outside/policy.pdf"))
    normalized = str(PureWindowsPath("E:/archive/policy.md"))
    adapted = adapt_v1_to_v2(
        legacy_metadata(source_path=source, normalized_path=normalized),
        "metadata",
        {
            "raw_root": PureWindowsPath("C:/known/raw"),
            "normalized_root": PureWindowsPath("C:/known/normalized"),
        },
    )

    assert adapted.legacy_source_path == source
    assert adapted.legacy_normalized_path == normalized
    assert adapted.legacy_path == source


def test_legacy_metadata_ocr_engine_is_retained_on_estimated_confidence() -> None:
    adapted = adapt_v1_to_v2(
        legacy_metadata(ocr_engine="legacy-tesseract", ocr_confidence=0.8),
        "metadata",
        {},
    )

    assert adapted.ocr_confidence.engine == "legacy-tesseract"


def test_unsafe_relative_legacy_path_has_traversal_specific_warning() -> None:
    adapted = adapt_v1_to_v2(
        legacy_metadata(source_path="../outside/policy.pdf"),
        "metadata",
        {},
    )

    assert "legacy_relative_path_unsafe" in adapted.warnings
    assert "legacy_absolute_path_not_relativized" not in adapted.warnings


def test_canonical_v2_payload_rejects_unknown_fields_in_loader() -> None:
    adapted = adapt_v1_to_v2(legacy_metadata(), "metadata", {})
    payload = adapted.model_dump(mode="json")
    payload["unexpected"] = "forbidden"

    with pytest.raises(ValidationError):
        load_artifact(payload, "metadata", {})
