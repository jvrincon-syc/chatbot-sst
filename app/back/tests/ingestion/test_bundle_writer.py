from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import ingestion.manifests.bundle_writer as bundle_writer_module
from ingestion.manifests.bundle_writer import BundlePayload, write_bundle_atomic
from ingestion.manifests.writer import dump_json_atomic, write_text_atomic
from ingestion.paths import ArtifactPaths, stable_document_id
from ingestion.schemas.artifacts import (
    Classification,
    DocumentControl,
    FormsArtifact,
    MetadataArtifact,
    OcrArtifact,
    PagesArtifact,
    TablesArtifact,
)
from ingestion.schemas.common import (
    ConfidenceMetric,
    DocumentField,
    Observation,
)
from ingestion.schemas.inventory import InventoryRecord
from ingestion.schemas.legacy_v1 import LegacyPagesArtifact
from ingestion.schemas.manifests import (
    ArtifactHash,
    BundleManifest,
    ErrorItem,
    ErrorManifest,
    InventoryManifest,
    ReviewItem,
    ReviewManifest,
    RunDocument,
    RunManifest,
)
from scripts.ingestion.export_schemas import SCHEMAS


def _unavailable_confidence() -> ConfidenceMetric:
    return ConfidenceMetric(kind="unavailable", value=None)


def _not_evaluated() -> Observation:
    return Observation(status="not_evaluated", value=None)


def _metadata(document_id: str, source_relpath: str) -> MetadataArtifact:
    paths = ArtifactPaths.for_source(source_relpath)
    return MetadataArtifact(
        schema_version="2.0",
        document_id=document_id,
        document_name=Path(source_relpath).name,
        source_relpath=source_relpath,
        normalized_relpath=paths.markdown,
        document_control=DocumentControl(
            title=DocumentField(value=None, status="not_evaluated"),
            code=DocumentField(value=None, status="not_evaluated"),
            version=DocumentField(value=None, status="not_evaluated"),
            publication_date=DocumentField(value=None, status="not_evaluated"),
            effective_date=DocumentField(value=None, status="not_evaluated"),
        ),
        classification=Classification(
            document_type="otro",
            document_type_confidence=ConfidenceMetric(
                kind="estimated", value=0.1, method="test"
            ),
            topic="unknown",
            topic_confidence=ConfidenceMetric(
                kind="estimated", value=0.1, method="test"
            ),
        ),
        page_count=0,
        extraction_method="pdf_digital",
        ocr_confidence=_unavailable_confidence(),
        handwriting=_not_evaluated(),
        tables=_not_evaluated(),
        forms=_not_evaluated(),
        source_hash="a" * 64,
        corpus_version="test",
        pipeline_version="2.0.0",
        processing_status="processed",
    )


def _bundle_payload(
    source_relpath: str = "manual/document.pdf",
    *,
    artifact_document_id: str | None = None,
) -> BundlePayload:
    document_id = stable_document_id(source_relpath)
    artifact_id = artifact_document_id or document_id
    paths = ArtifactPaths.for_source(source_relpath)
    return BundlePayload(
        document_id=document_id,
        source_relpath=source_relpath,
        source_hash="a" * 64,
        processing_fingerprint="pipeline:test",
        document_status="processed",
        artifacts={
            paths.markdown: "# Document\n",
            paths.metadata: _metadata(artifact_id, source_relpath),
            paths.pages: PagesArtifact(
                schema_version="2.0",
                document_id=artifact_id,
                page_count=0,
                pages=[],
            ),
            paths.ocr: OcrArtifact(
                schema_version="2.0",
                document_id=artifact_id,
                document_confidence=_unavailable_confidence(),
                pages=[],
            ),
            paths.tables: TablesArtifact(
                schema_version="2.0",
                document_id=artifact_id,
                table_count=0,
                tables=[],
            ),
            paths.forms: FormsArtifact(
                schema_version="2.0",
                document_id=artifact_id,
            ),
        },
    )


def _inventory_record() -> InventoryRecord:
    return InventoryRecord(
        schema_version="2.0",
        document_id="doc_1",
        source_relpath="manual/document.pdf",
        document_name="document.pdf",
        detected_extension=".pdf",
        reported_extension=".pdf",
        mime_type="application/pdf",
        content_hash="a" * 64,
        file_size=10,
        ingestion_date="2026-07-17T00:00:00Z",
        category_inferred="manual",
        pipeline_version="2.0.0",
        corpus_version="test",
    )


def test_manifest_models_are_strict_schema_2_envelopes() -> None:
    inventory = InventoryManifest(
        schema_version="2.0",
        generated_at="2026-07-17T00:00:00Z",
        corpus_version="test",
        pipeline_version="2.0.0",
        records=[_inventory_record()],
    )
    run_document = RunDocument(
        schema_version="2.0",
        document_id="doc_1",
        source_relpath="manual/document.pdf",
        document_status="processed",
        disposition="reused",
    )
    paths = ArtifactPaths.for_source("manual/document.pdf")
    bundle = BundleManifest(
        schema_version="2.0",
        document_id="doc_1",
        source_relpath="manual/document.pdf",
        source_hash="a" * 64,
        normalized_base=paths.normalized_base,
        required_artifacts=list(paths.required_relpaths()),
        artifact_hashes=[
            ArtifactHash(
                schema_version="2.0",
                relpath=relpath,
                sha256="0" * 64,
                byte_size=0,
            )
            for relpath in paths.required_relpaths()
        ],
        processing_fingerprint="pipeline:test",
        document_status="processed",
    )
    run = RunManifest(
        schema_version="2.0",
        run_id="run-1",
        timestamp="2026-07-17T00:00:00Z",
        fingerprints={"processing": "pipeline:test"},
        summary={"reused": 1},
        documents=[run_document],
        bundles=[bundle],
    )
    review = ReviewManifest(
        schema_version="2.0",
        run_id="run-1",
        generated_at="2026-07-17T00:00:00Z",
        items=[
            ReviewItem(
                schema_version="2.0",
                document_id="doc_1",
                source_relpath="manual/document.pdf",
                reasons=["low_confidence"],
            )
        ],
    )
    errors = ErrorManifest(
        schema_version="2.0",
        run_id="run-1",
        generated_at="2026-07-17T00:00:00Z",
        items=[
            ErrorItem(
                schema_version="2.0",
                document_id="doc_1",
                source_relpath="manual/document.pdf",
                stage="extract",
                error_type="RuntimeError",
                message="failed",
            )
        ],
    )

    assert inventory.records[0].source_relpath == "manual/document.pdf"
    assert run.documents[0].disposition == "reused"
    assert review.items[0].reasons == ["low_confidence"]
    assert errors.items[0].stage == "extract"
    with pytest.raises(ValidationError):
        InventoryManifest(**{**inventory.model_dump(), "unexpected": True})
    with pytest.raises(ValidationError):
        RunDocument(**{**run_document.model_dump(), "disposition": "skipped"})
    with pytest.raises(ValidationError):
        RunDocument(
            document_id="doc_1",
            source_relpath="manual/document.pdf",
            document_status="processed",
            disposition="reused",
        )


def test_bundle_manifest_requires_source_derived_artifact_paths() -> None:
    with pytest.raises(ValidationError, match="normalized_base"):
        BundleManifest(
            schema_version="2.0",
            document_id="doc_1",
            source_relpath="manual/document.pdf",
            source_hash="a" * 64,
            normalized_base="wrong/base",
            required_artifacts=["elsewhere.txt"],
            artifact_hashes=[
                ArtifactHash(
                    schema_version="2.0",
                    relpath="elsewhere.txt",
                    sha256="0" * 64,
                    byte_size=0,
                )
            ],
            processing_fingerprint="pipeline:test",
            document_status="processed",
        )

    with pytest.raises(ValidationError, match="required_artifacts"):
        BundleManifest(
            schema_version="2.0",
            document_id="doc_1",
            source_relpath="manual/document.pdf",
            source_hash="a" * 64,
            normalized_base="manual/document",
            required_artifacts=["elsewhere.txt"],
            artifact_hashes=[
                ArtifactHash(
                    schema_version="2.0",
                    relpath="elsewhere.txt",
                    sha256="0" * 64,
                    byte_size=0,
                )
            ],
            processing_fingerprint="pipeline:test",
            document_status="processed",
        )


def test_schema_export_includes_all_canonical_artifacts_and_manifests() -> None:
    assert set(SCHEMAS) == {
        "metadata.schema.json",
        "pages.schema.json",
        "ocr.schema.json",
        "tables.schema.json",
        "forms.schema.json",
        "inventory.schema.json",
        "run.schema.json",
        "review.schema.json",
        "errors.schema.json",
        "bundle.schema.json",
    }
    assert all(
        model.model_json_schema().get("additionalProperties") is False
        for model in SCHEMAS.values()
    )


def test_dump_json_atomic_writes_a_versioned_inventory_envelope(
    tmp_path: Path,
) -> None:
    target = tmp_path / "inventory.json"
    manifest = InventoryManifest(
        schema_version="2.0",
        generated_at="2026-07-17T00:00:00Z",
        corpus_version="test",
        pipeline_version="2.0.0",
        records=[_inventory_record()],
    )

    dump_json_atomic(target, manifest)

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "2.0"
    assert isinstance(payload["records"], list)
    assert payload["records"][0]["source_relpath"] == "manual/document.pdf"


@pytest.mark.parametrize(
    "legacy",
    [
        {"schema_version": "1.0", "document_id": "doc_1", "page_count": 0, "pages": []},
        LegacyPagesArtifact(
            schema_version="1.0",
            document_id="doc_1",
            page_count=0,
            pages=[],
        ),
    ],
)
def test_dump_json_atomic_refuses_legacy_outputs(
    tmp_path: Path, legacy: object
) -> None:
    target = tmp_path / "pages.json"
    target.write_text('{"existing": true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="canonical schema 2.0"):
        dump_json_atomic(target, legacy)

    assert target.read_text(encoding="utf-8") == '{"existing": true}\n'
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_dump_json_atomic_refuses_standalone_inventory_record(tmp_path: Path) -> None:
    target = tmp_path / "inventory.json"

    with pytest.raises(ValueError, match="canonical schema 2.0"):
        dump_json_atomic(target, _inventory_record())

    assert not target.exists()


def test_atomic_replace_failure_preserves_existing_target_and_removes_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "document.md"
    target.write_text("old", encoding="utf-8")

    def fail_replace(source: object, destination: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("ingestion.manifests.writer.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_text_atomic(target, "new")

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_failure_preserves_existing_target_and_removes_temp(
    tmp_path: Path,
) -> None:
    target = tmp_path / "document.md"
    target.write_text("old", encoding="utf-8")

    with pytest.raises(UnicodeEncodeError):
        write_text_atomic(target, "invalid surrogate: \ud800")

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_write_bundle_atomic_writes_required_files_and_hashes_final_bytes(
    tmp_path: Path,
) -> None:
    payload = _bundle_payload()

    manifest = write_bundle_atomic(tmp_path, payload)

    expected_relpaths = set(
        ArtifactPaths.for_source(payload.source_relpath).required_relpaths()
    )
    assert set(manifest.required_artifacts) == expected_relpaths
    assert {item.relpath for item in manifest.artifact_hashes} == expected_relpaths
    assert set(
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file()
    ) == expected_relpaths
    for artifact_hash in manifest.artifact_hashes:
        artifact_path = tmp_path / Path(artifact_hash.relpath)
        final_bytes = artifact_path.read_bytes()
        assert artifact_hash.sha256 == hashlib.sha256(final_bytes).hexdigest()
        assert artifact_hash.byte_size == len(final_bytes)


def test_write_bundle_atomic_accepts_a_strict_mapping_payload(tmp_path: Path) -> None:
    typed = _bundle_payload()
    payload = {
        "document_id": typed.document_id,
        "source_relpath": typed.source_relpath,
        "source_hash": typed.source_hash,
        "processing_fingerprint": typed.processing_fingerprint,
        "document_status": typed.document_status,
        "artifacts": typed.artifacts,
    }

    manifest = write_bundle_atomic(tmp_path, payload)

    assert manifest.document_id == typed.document_id


def test_write_bundle_atomic_rejects_artifact_document_id_mismatch_before_write(
    tmp_path: Path,
) -> None:
    payload = _bundle_payload(artifact_document_id="doc_wrong")

    with pytest.raises(ValueError, match="document ID"):
        write_bundle_atomic(tmp_path, payload)

    assert list(tmp_path.rglob("*")) == []


def test_write_bundle_atomic_rejects_wrong_model_for_artifact_relpath(
    tmp_path: Path,
) -> None:
    payload = _bundle_payload()
    paths = ArtifactPaths.for_source(payload.source_relpath)
    payload.artifacts[paths.pages] = _inventory_record().model_copy(
        update={
            "document_id": payload.document_id,
            "source_relpath": payload.source_relpath,
        }
    )

    with pytest.raises(TypeError, match="PagesArtifact"):
        write_bundle_atomic(tmp_path, payload)

    assert list(tmp_path.rglob("*")) == []


def test_write_bundle_atomic_validates_manifest_fields_before_write(
    tmp_path: Path,
) -> None:
    payload = _bundle_payload()
    payload.source_hash = "not-a-sha256"

    with pytest.raises(ValidationError):
        write_bundle_atomic(tmp_path, payload)

    assert list(tmp_path.rglob("*")) == []


def test_write_bundle_atomic_rejects_traversing_artifact_relpath(
    tmp_path: Path,
) -> None:
    payload = _bundle_payload()
    payload.artifacts["../outside.md"] = payload.artifacts.pop(
        ArtifactPaths.for_source(payload.source_relpath).markdown
    )

    with pytest.raises(ValueError):
        write_bundle_atomic(tmp_path, payload)

    assert not (tmp_path.parent / "outside.md").exists()


def test_write_bundle_atomic_rejects_symlink_escape(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    candidate = tmp_path / "candidate"
    outside.mkdir()
    candidate.mkdir()
    try:
        (candidate / "manual").symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(ValueError, match="symlinks"):
        write_bundle_atomic(candidate, _bundle_payload("manual/document.pdf"))

    assert not (outside / "document.md").exists()


def test_write_bundle_atomic_rejects_symlink_inserted_during_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    candidate = tmp_path / "candidate"
    outside.mkdir()
    candidate.mkdir()
    original_write = bundle_writer_module._write_text_secure
    swapped = False

    def swap_directory_then_write(root_fd: int, relpath: str, text: str) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            (candidate / "manual").symlink_to(outside, target_is_directory=True)
        original_write(root_fd, relpath, text)

    monkeypatch.setattr(
        bundle_writer_module,
        "_write_text_secure",
        swap_directory_then_write,
    )

    with pytest.raises(ValueError, match="escapes candidate root"):
        write_bundle_atomic(candidate, _bundle_payload("manual/document.pdf"))

    assert not (outside / "document.md").exists()


def test_write_bundle_atomic_rolls_back_when_later_artifact_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _bundle_payload()
    original_write = bundle_writer_module._write_text_secure
    calls = 0

    def fail_second_write(root_fd: int, relpath: str, text: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("artifact write failed")
        original_write(root_fd, relpath, text)

    monkeypatch.setattr(
        bundle_writer_module,
        "_write_text_secure",
        fail_second_write,
    )

    with pytest.raises(OSError, match="artifact write failed"):
        write_bundle_atomic(tmp_path, payload)

    assert [path for path in tmp_path.rglob("*") if path.is_file()] == []
