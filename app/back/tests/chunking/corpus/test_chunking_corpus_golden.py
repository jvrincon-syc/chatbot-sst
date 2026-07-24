from __future__ import annotations

import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from ingestion.paths import ArtifactPaths
from scripts.chunking.validate_chunks import validate_chunk_outputs


SOURCE_HASH = "d" * 64
EXPECTED_PATH = Path("docs/chunking/golden_corpus_expected.json")


def _sandbox(name: str) -> tuple[Path, Path, Path]:
    root = Path("manual-test-temp") / "chunking-corpus-golden" / f"{name}-{uuid4().hex}"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    docs_root = root / "docs_normalized"
    chunks_root = root / "chunks"
    openapi_output = root / "openapi.json"
    docs_root.mkdir(parents=True, exist_ok=True)
    chunks_root.mkdir(parents=True, exist_ok=True)
    return docs_root, chunks_root, openapi_output


def _confidence(*, value: float | None = None, kind: str = "unavailable") -> dict[str, object]:
    return {
        "kind": kind,
        "value": value,
        "unit": None,
        "method": "fixture_estimate" if kind == "estimated" else None,
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


def _document_field() -> dict[str, object]:
    return {
        "value": None,
        "value_raw": None,
        "status": "not_found",
        "evidence": [],
        "warnings": [],
    }


def _write_document(
    docs_root: Path,
    *,
    document_id: str,
    source_relpath: str,
    markdown_pages: list[tuple[int, str]],
    tables_payload: dict[str, object] | None = None,
    forms_payload: dict[str, object] | None = None,
    ocr_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    artifact_paths = ArtifactPaths.for_source(source_relpath)
    markdown_path = docs_root / artifact_paths.markdown
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_body = "".join(
        f"<!-- page: {page_number} -->\n{text.strip()}\n\n"
        for page_number, text in markdown_pages
    ).rstrip() + "\n"
    markdown = (
        "---\n"
        f"document_id: {document_id}\n"
        f"source_relpath: {source_relpath}\n"
        f"source_hash: {SOURCE_HASH}\n"
        "---\n"
        f"{markdown_body}"
    )
    markdown_path.write_text(markdown, encoding="utf-8")
    metadata = {
        "schema_version": "2.0",
        "document_id": document_id,
        "document_name": Path(source_relpath).name,
        "source_relpath": source_relpath,
        "normalized_relpath": artifact_paths.markdown,
        "document_control": {
            "title": _document_field(),
            "code": _document_field(),
            "version": _document_field(),
            "publication_date": _document_field(),
            "effective_date": _document_field(),
        },
        "classification": {
            "document_type": "procedimiento",
            "document_type_confidence": _confidence(),
            "topic": "SST",
            "topic_confidence": _confidence(),
        },
        "page_count": len(markdown_pages),
        "extraction_method": "markdown",
        "ocr_confidence": _confidence(),
        "handwriting": _observation(),
        "tables": _observation(),
        "forms": _observation(),
        "source_hash": SOURCE_HASH,
        "corpus_version": "golden-corpus-v1",
        "pipeline_version": "2.0.0",
        "processing_status": "processed",
    }
    pages = {
        "schema_version": "2.0",
        "document_id": document_id,
        "page_count": len(markdown_pages),
        "pages": [
            {
                "page_number": page_number,
                "text_raw": text.strip(),
                "text_normalized": text.strip(),
                "extraction_method": "markdown",
                "blocks": [],
                "ocr_confidence": _confidence(),
            }
            for page_number, text in markdown_pages
        ],
    }
    markdown_path.with_suffix(".metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    markdown_path.with_suffix(".pages.json").write_text(
        json.dumps(pages), encoding="utf-8"
    )
    if tables_payload is not None:
        markdown_path.with_suffix(".tables.json").write_text(
            json.dumps(tables_payload), encoding="utf-8"
        )
    if forms_payload is not None:
        markdown_path.with_suffix(".forms.json").write_text(
            json.dumps(forms_payload), encoding="utf-8"
        )
    if ocr_payload is not None:
        markdown_path.with_suffix(".ocr.json").write_text(
            json.dumps(ocr_payload), encoding="utf-8"
        )
    return {
        "document_id": document_id,
        "source_relpath": source_relpath,
        "processing_status": "processed",
        "source_hash": SOURCE_HASH,
        "document_name": Path(source_relpath).name,
    }


def _write_inventory(docs_root: Path, records: list[dict[str, object]]) -> None:
    manifests = docs_root / "_manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "inventory.json").write_text(
        json.dumps({"records": records}), encoding="utf-8"
    )


def _case_records(docs_root: Path) -> list[dict[str, object]]:
    records = []
    records.append(
        _write_document(
            docs_root,
            document_id="golden_manual_headings",
            source_relpath="golden/manual_headings.md",
            markdown_pages=[
                (
                    1,
                    "# Manual SST\n\n## Objetivo\n"
                    "Definir responsabilidades con evidencia trazable.\n\n"
                    "## Responsabilidades\n"
                    "Cada lider debe conservar soporte documental.",
                )
            ],
        )
    )
    records.append(
        _write_document(
            docs_root,
            document_id="golden_reglamento_articulos",
            source_relpath="golden/reglamento_articulos.md",
            markdown_pages=[
                (
                    1,
                    "# Reglamento\n\n## Articulo 1\n"
                    "Primera regla del reglamento.\n\n"
                    "## Articulo 2\n"
                    "Segunda regla del reglamento.\n\n"
                    "## Articulo 3\n"
                    "Tercera regla del reglamento.",
                )
            ],
        )
    )
    records.append(
        _write_document(
            docs_root,
            document_id="golden_sin_headings",
            source_relpath="golden/sin_headings.md",
            markdown_pages=[
                (
                    1,
                    "Texto corrido sin encabezados visibles pero con trazabilidad y contexto "
                    "suficiente para generar un unico parent estructural.",
                )
            ],
        )
    )
    records.append(
        _write_document(
            docs_root,
            document_id="golden_mixto_ruido",
            source_relpath="golden/mixto_ruido.md",
            markdown_pages=[
                (
                    1,
                    "# Procedimiento mixto\n\n## Preparacion\n"
                    "- revisar formatos\n- validar evidencia\n\n"
                    "NOTA INTERNA SST\n\n"
                    "## Cierre\n"
                    "Registrar novedades y firmar acta.",
                )
            ],
        )
    )
    records.append(
        _write_document(
            docs_root,
            document_id="golden_procedimiento_largo",
            source_relpath="golden/procedimiento_largo.md",
            markdown_pages=[
                (
                    1,
                    "# Procedimiento largo\n\n"
                    + " ".join(
                        [
                            "La evidencia del procedimiento debe conservarse con trazabilidad completa."
                            for _ in range(160)
                        ]
                    ),
                )
            ],
        )
    )
    records.append(
        _write_document(
            docs_root,
            document_id="golden_formulario",
            source_relpath="golden/formulario.md",
            markdown_pages=[
                (
                    1,
                    "# Formulario de inspeccion\n\n"
                    "Nombre: ____\nFecha: ____\nArea: ____\n[ ] Conforme\n[ ] No conforme",
                )
            ],
            forms_payload={
                "schema_version": "2.0",
                "document_id": "golden_formulario",
                "groups": [
                    {
                        "group_id": "form-1",
                        "page_number": 1,
                        "title": "Formulario de inspeccion",
                    }
                ],
            },
        )
    )
    records.append(
        _write_document(
            docs_root,
            document_id="golden_tabla_extensa",
            source_relpath="golden/tabla_extensa.md",
            markdown_pages=[
                (
                    1,
                    "# Tabla de seguimiento\n\n"
                    "| Riesgo | Control |\n| --- | --- |\n| Caidas | Inspeccion |\n| Ruido | Medicion |",
                )
            ],
            tables_payload={
                "schema_version": "2.0",
                "document_id": "golden_tabla_extensa",
                "table_count": 1,
                "tables": [
                    {
                        "table_id": "table-1",
                        "page_number": 1,
                        "bbox": None,
                        "markdown_representation": (
                            "| Riesgo | Control |\n| --- | --- |\n| Caidas | Inspeccion |\n| Ruido | Medicion |"
                        ),
                        "extractor": "markdown",
                        "quality": _confidence(),
                    }
                ],
            },
        )
    )
    records.append(
        _write_document(
            docs_root,
            document_id="golden_ocr_imperfecto",
            source_relpath="golden/ocr_imperfecto.md",
            markdown_pages=[
                (1, "# OCR\n\nTexto reconstruido con calidad limitada pero utilizable.")
            ],
            ocr_payload={
                "schema_version": "2.0",
                "document_id": "golden_ocr_imperfecto",
                "document_confidence": _confidence(value=0.61, kind="estimated"),
                "pages": [],
            },
        )
    )
    records.append(
        _write_document(
            docs_root,
            document_id="golden_seccion_multiplagina",
            source_relpath="golden/seccion_multiplagina.md",
            markdown_pages=[
                (
                    1,
                    "# Seccion transversal\n\n"
                    "La seccion empieza en la primera pagina y conserva continuidad documental.",
                ),
                (
                    2,
                    "La misma seccion continua en la segunda pagina sin un nuevo encabezado.",
                ),
            ],
        )
    )
    records.append(
        _write_document(
            docs_root,
            document_id="golden_literal_critico",
            source_relpath="golden/literal_critico.md",
            markdown_pages=[
                (
                    1,
                    "# Literales criticos\n\n"
                    "Codigo PRO-SST-777. Porcentaje requerido 95%. Fecha efectiva 2026-07-24.",
                )
            ],
        )
    )
    return records


@pytest.mark.corpus
def test_validate_chunks_recorre_golden_y_exporta_openapi() -> None:
    docs_root, chunks_root, openapi_output = _sandbox("golden")
    records = _case_records(docs_root)
    _write_inventory(docs_root, records)

    result = validate_chunk_outputs(
        docs_normalized=docs_root,
        chunks_root=chunks_root,
        expected_json=EXPECTED_PATH,
        openapi_output=openapi_output,
        compare_rerun=True,
    )

    assert result["documents_checked"] == 10
    assert result["docs_unchanged"] is True
    assert openapi_output.exists()
    assert any(
        document["document_id"] == "golden_procedimiento_largo" and document["child_count"] >= 2
        for document in result["documents"]
    )
