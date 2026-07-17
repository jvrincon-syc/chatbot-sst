from pathlib import Path

from ingestion.inventory.scanner import scan_docs_raw


def test_scan_docs_raw_inventories_all_files_and_detects_duplicates(tmp_path: Path) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    folder = docs_raw / "copasst"
    folder.mkdir(parents=True)
    (folder / "funciones.md").write_text("# Funciones\n\nContenido", encoding="utf-8")
    (folder / "funciones_copy.md").write_text("# Funciones\n\nContenido", encoding="utf-8")
    (folder / "sin_extension").write_bytes(b"%PDF-1.4\n% fake pdf")

    records = scan_docs_raw(docs_raw, corpus_version="test", pipeline_version="1.0.0")

    assert len(records) == 3
    assert {record.schema_version for record in records} == {"2.0"}
    assert {record.identity_version for record in records} == {"relpath-posix-v1"}
    assert {record.processing_status for record in records} == {"pending"}
    assert all(record.document_id.startswith("doc_") for record in records)
    assert {record.category_inferred for record in records} == {"copasst"}
    assert {record.source_relpath for record in records} == {
        "copasst/funciones.md",
        "copasst/funciones_copy.md",
        "copasst/sin_extension",
    }
    assert all("source_path" not in record.model_dump() for record in records)

    hashes = [record.content_hash for record in records]
    assert hashes.count(hashes[0]) == 2

    extensionless = next(record for record in records if record.document_name == "sin_extension")
    assert extensionless.reported_extension is None
    assert extensionless.detected_extension == ".pdf"
    assert extensionless.mime_type == "application/pdf"


def test_scan_docs_raw_keeps_document_ids_stable_for_same_path_and_hash(tmp_path: Path) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    docs_raw.mkdir(parents=True)
    (docs_raw / "documento.md").write_text("# Titulo\n", encoding="utf-8")

    first = scan_docs_raw(docs_raw, corpus_version="test", pipeline_version="1.0.0")
    second = scan_docs_raw(docs_raw, corpus_version="test", pipeline_version="1.0.0")

    assert first[0].document_id == second[0].document_id


def test_scan_docs_raw_keeps_document_id_stable_when_same_file_changes(tmp_path: Path) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    source = docs_raw / "documento.md"
    docs_raw.mkdir(parents=True)
    source.write_text("# Titulo\n", encoding="utf-8")

    first = scan_docs_raw(docs_raw, corpus_version="test", pipeline_version="1.0.0")
    source.write_text("# Titulo\n\nContenido actualizado\n", encoding="utf-8")
    second = scan_docs_raw(docs_raw, corpus_version="test", pipeline_version="1.0.0")

    assert first[0].document_id == second[0].document_id
    assert first[0].content_hash != second[0].content_hash


def test_scan_docs_raw_identity_is_stable_after_moving_raw_root(tmp_path: Path) -> None:
    first_root = tmp_path / "first" / "docs_raw"
    moved_root = tmp_path / "moved" / "docs_raw"
    source_relpath = Path("manual") / "documento.pdf"
    (first_root / source_relpath).parent.mkdir(parents=True)
    (moved_root / source_relpath).parent.mkdir(parents=True)
    content = b"%PDF-1.4\nportable"
    (first_root / source_relpath).write_bytes(content)
    (moved_root / source_relpath).write_bytes(content)

    first = scan_docs_raw(first_root, corpus_version="test", pipeline_version="2.0.0")
    moved = scan_docs_raw(moved_root, corpus_version="test", pipeline_version="2.0.0")

    assert first[0].source_relpath == moved[0].source_relpath == "manual/documento.pdf"
    assert first[0].document_id == moved[0].document_id
