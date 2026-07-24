from __future__ import annotations

import json
from pathlib import Path

import pytest

from chunking.infrastructure.schema2_source import Schema2NormalizedDocumentSource


DOCUMENT_ID = "doc_schema2_source"
SOURCE_HASH = "a" * 64
RELATIVE_PATH = "manuales/procedimiento.md"


def _confidence() -> dict[str, object]:
    return {
        "kind": "unavailable",
        "value": None,
        "unit": None,
        "method": None,
        "engine": None,
        "engine_version": None,
        "sample_size": None,
        "provenance": None,
        "warnings": [],
    }


def _observation() -> dict[str, object]:
    return {
        "status": "not_evaluated",
        "value": None,
        "method": None,
        "engine": None,
        "engine_version": None,
        "evidence": [],
        "warnings": [],
    }


def _metadata() -> dict[str, object]:
    document_field = {
        "value": None,
        "value_raw": None,
        "status": "not_found",
        "evidence": [],
        "warnings": [],
    }
    return {
        "schema_version": "2.0",
        "document_id": DOCUMENT_ID,
        "document_name": "procedimiento.md",
        "source_relpath": RELATIVE_PATH,
        "normalized_relpath": RELATIVE_PATH,
        "document_control": {
            "title": document_field,
            "code": document_field,
            "version": document_field,
            "publication_date": document_field,
            "effective_date": document_field,
        },
        "classification": {
            "document_type": "procedimiento",
            "document_type_confidence": _confidence(),
            "topic": "SST",
            "topic_confidence": _confidence(),
        },
        "page_count": 2,
        "extraction_method": "markdown",
        "ocr_confidence": _confidence(),
        "handwriting": _observation(),
        "tables": _observation(),
        "forms": _observation(),
        "source_hash": SOURCE_HASH,
        "corpus_version": "corpus-v2",
        "pipeline_version": "2.0.0",
        "processing_status": "processed",
    }


def _pages(
    *,
    first_text: str = "Codigo SST-01",
    second_text: str = "Fecha 2026-07-23",
    page_numbers: tuple[int, int] = (1, 2),
) -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "document_id": DOCUMENT_ID,
        "page_count": 2,
        "pages": [
            {
                "page_number": page_numbers[0],
                "text_raw": first_text,
                "text_normalized": first_text,
                "extraction_method": "markdown",
                "blocks": [],
                "ocr_confidence": _confidence(),
            },
            {
                "page_number": page_numbers[1],
                "text_raw": second_text,
                "text_normalized": second_text,
                "extraction_method": "markdown",
                "blocks": [],
                "ocr_confidence": _confidence(),
            },
        ],
    }


def _write_bundle(
    root: Path,
    *,
    markdown: str,
    pages: dict[str, object] | None = None,
    metadata: dict[str, object] | None = None,
    optional_sidecars: tuple[str, ...] = (),
) -> Path:
    markdown_path = root / RELATIVE_PATH
    markdown_path.parent.mkdir(parents=True)
    resolved_metadata = metadata or _metadata()
    if not markdown.startswith("---\n"):
        markdown = (
            "---\n"
            f"document_id: {resolved_metadata['document_id']}\n"
            f"source_relpath: {resolved_metadata['source_relpath']}\n"
            "---\n"
            f"{markdown}"
        )
    markdown_path.write_text(markdown, encoding="utf-8")
    markdown_path.with_suffix(".metadata.json").write_text(
        json.dumps(resolved_metadata), encoding="utf-8"
    )
    markdown_path.with_suffix(".pages.json").write_text(
        json.dumps(pages or _pages()), encoding="utf-8"
    )
    for artifact_name in optional_sidecars:
        payload: dict[str, object] = {
            "schema_version": "2.0",
            "document_id": DOCUMENT_ID,
        }
        if artifact_name == "tables":
            payload.update({"table_count": 0, "tables": []})
        elif artifact_name == "forms":
            payload["groups"] = []
        elif artifact_name == "ocr":
            payload.update({"document_confidence": _confidence(), "pages": []})
        else:
            raise AssertionError(f"unsupported sidecar: {artifact_name}")
        markdown_path.with_suffix(f".{artifact_name}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    return markdown_path


def test_loads_complete_sidecars_and_prefers_markdown_page_markers(tmp_path: Path) -> None:
    markdown = (
        "---\n"
        f"document_id: {DOCUMENT_ID}\n"
        f"source_relpath: {RELATIVE_PATH}\n"
        f"source_hash: {SOURCE_HASH}\n"
        "---\n"
        "<!-- page: 4 -->\nCodigo SST-01\n"
        "<!-- page: 9 -->\nFecha 2026-07-23\n"
    )
    _write_bundle(
        tmp_path,
        markdown=markdown,
        pages=_pages(page_numbers=(4, 9)),
        optional_sidecars=("tables", "forms", "ocr"),
    )
    markdown_path = tmp_path / RELATIVE_PATH
    markdown_path.with_suffix(".tables.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "document_id": DOCUMENT_ID,
                "table_count": 1,
                "tables": [
                    {
                        "table_id": "table-1",
                        "page_number": 4,
                        "bbox": None,
                            "markdown_representation": "| Codigo |\n| SST-01 |",
                        "extractor": "markdown",
                        "quality": _confidence(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    markdown_path.with_suffix(".forms.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "document_id": DOCUMENT_ID,
                "groups": [
                    {
                        "group_id": "form-1",
                        "page_number": 9,
                        "title": "Aprobacion",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    document = Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)

    assert document.markdown == markdown
    assert document.structural_blocks == ()
    assert [trace.page_number for trace in document.page_traces] == [4, 9]
    assert document.page_traces[0].text_normalized == "Codigo SST-01"
    assert document.sidecars.tables_present is True
    assert document.sidecars.forms_present is True
    assert document.sidecars.ocr_present is True
    assert document.sidecars.table_markdown == ("| Codigo |\n| SST-01 |",)
    assert document.sidecars.form_titles == ("Aprobacion",)
    assert document.warnings == ()


def test_loads_incomplete_and_absent_optional_sidecars_without_inventing_values(tmp_path: Path) -> None:
    markdown = "Codigo SST-01\n\nFecha 2026-07-23\n"
    _write_bundle(tmp_path, markdown=markdown, optional_sidecars=("forms",))

    document = Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)

    assert [trace.page_number for trace in document.page_traces] == [1, 2]
    assert document.sidecars.tables_present is False
    assert document.sidecars.forms_present is True
    assert document.sidecars.ocr_present is False
    assert document.sidecars.ocr_confidence is None
    assert document.structural_blocks == ()


def test_emits_unresolved_warning_when_pages_cannot_be_safely_aligned(tmp_path: Path) -> None:
    _write_bundle(
        tmp_path,
        markdown="Contenido que no coincide con las paginas\n",
        pages=_pages(first_text="Primera pagina", second_text="Segunda pagina"),
    )

    document = Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)

    assert document.page_traces == ()
    assert document.warnings == ("PAGE_TRACE_UNRESOLVED",)


def test_emits_unresolved_warning_for_marker_page_absent_from_pages_sidecar(tmp_path: Path) -> None:
    _write_bundle(
        tmp_path,
        markdown=(
            "<!-- page: 3 -->\nCodigo SST-01\n"
            "<!-- page: 4 -->\nFecha 2026-07-23\n"
        ),
    )

    document = Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)

    assert document.page_traces == ()
    assert document.warnings == ("PAGE_TRACE_UNRESOLVED",)


def test_emits_unresolved_warning_for_duplicate_page_numbers_in_pages_sidecar(tmp_path: Path) -> None:
    _write_bundle(
        tmp_path,
        markdown="<!-- page: 1 -->\nCodigo SST-01\n",
        pages=_pages(page_numbers=(1, 1)),
    )

    document = Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)

    assert document.page_traces == ()
    assert document.warnings == ("PAGE_TRACE_UNRESOLVED",)


def test_emits_unresolved_warning_for_out_of_order_markers(tmp_path: Path) -> None:
    _write_bundle(
        tmp_path,
        markdown=(
            "<!-- page: 2 -->\nCodigo SST-01\n"
            "<!-- page: 1 -->\nFecha 2026-07-23\n"
        ),
        pages=_pages(page_numbers=(1, 2)),
    )

    document = Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)

    assert document.page_traces == ()
    assert document.warnings == ("PAGE_TRACE_UNRESOLVED",)


def test_rejects_front_matter_source_relpath_mismatch(tmp_path: Path) -> None:
    _write_bundle(
        tmp_path,
        markdown=(
            "---\n"
            f"document_id: {DOCUMENT_ID}\n"
            "source_relpath: otra/ruta.pdf\n"
            "---\n"
            "Codigo SST-01\n"
        ),
    )

    with pytest.raises(ValueError, match="source_relpath"):
        Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)


def test_rejects_metadata_and_pages_sidecars_with_different_page_counts(tmp_path: Path) -> None:
    metadata = _metadata()
    metadata["page_count"] = 1
    _write_bundle(tmp_path, markdown="Codigo SST-01\n\nFecha 2026-07-23\n", metadata=metadata)

    with pytest.raises(ValueError, match="page_count"):
        Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)


def test_rejects_sidecar_symlink_that_escapes_normalized_root(tmp_path: Path) -> None:
    markdown_path = _write_bundle(tmp_path, markdown="Codigo SST-01\n\nFecha 2026-07-23\n")
    outside_sidecar = tmp_path.parent / "outside.metadata.json"
    outside_sidecar.write_text(json.dumps(_metadata()), encoding="utf-8")
    metadata_path = markdown_path.with_suffix(".metadata.json")
    metadata_path.unlink()
    try:
        metadata_path.symlink_to(outside_sidecar)
    except OSError as error:
        pytest.skip(f"symlinks are unavailable in this test environment: {error}")

    with pytest.raises(ValueError, match="outside docs_normalized"):
        Schema2NormalizedDocumentSource(tmp_path).load(RELATIVE_PATH)


@pytest.mark.parametrize(
    ("path", "expected_error"),
    [
        ("../procedimiento.md", "unsafe"),
        ("manuales/../../procedimiento.md", "unsafe"),
    ],
)
def test_rejects_path_traversal(tmp_path: Path, path: str, expected_error: str) -> None:
    with pytest.raises(ValueError, match=expected_error):
        Schema2NormalizedDocumentSource(tmp_path).load(path)


def test_rejects_document_outside_normalized_root_and_inconsistent_identity(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    _write_bundle(tmp_path, markdown="<!-- page: 1 -->\nCodigo SST-01\n")
    bad_pages = _pages()
    bad_pages["document_id"] = "doc_other"
    (tmp_path / RELATIVE_PATH).with_suffix(".pages.json").write_text(
        json.dumps(bad_pages), encoding="utf-8"
    )

    source = Schema2NormalizedDocumentSource(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        source.load(outside)
    with pytest.raises(ValueError, match="document_id"):
        source.load(RELATIVE_PATH)
