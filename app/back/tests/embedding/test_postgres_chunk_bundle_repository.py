from __future__ import annotations

from embedding.domain.models import ChunkBundleRef
from embedding.infrastructure.postgres.repositories import PostgresChunkBundleRepository


def test_reconcilia_fila_legacy_antes_de_registrar_el_bundle_canonico() -> None:
    connection = ChunkBundleRecordingConnection(
        fetchone_results=[
            {
                "chunk_bundle_id": "legacy-chunk-bundle-abc",
                "project_id": "proj_alpha",
                "bundle_fingerprint": "chunk-bundle-abc",
                "profile_id": "local-structural-v1",
                "profile_fingerprint": "legacy-profile",
                "corpus_version": "phase1-main",
                "source_document_id": "doc_1",
                "artifact_relpath": "legacy.md",
                "parent_count": 0,
                "child_count": 0,
                "status": "legacy_unverified",
            },
            {
                "chunk_bundle_id": "chunk-bundle-abc",
                "project_id": "proj_alpha",
                "bundle_fingerprint": "chunk-bundle-abc",
                "profile_id": "local-structural-v1",
                "profile_fingerprint": "chunking-profile-abc",
                "corpus_version": "phase1-main",
                "source_document_id": "doc_1",
                "artifact_relpath": "unit/example.chunking_metadata.json",
                "parent_count": 1,
                "child_count": 2,
                "status": "verified",
            },
        ]
    )
    repository = PostgresChunkBundleRepository(connection)

    stored = repository.ensure_registered(
        ChunkBundleRef(
            chunk_bundle_id="chunk-bundle-abc",
            project_id="proj_alpha",
            bundle_fingerprint="chunk-bundle-abc",
            profile_id="local-structural-v1",
            profile_fingerprint="chunking-profile-abc",
            corpus_version="phase1-main",
            source_document_id="doc_1",
            artifact_relpath="unit/example.chunking_metadata.json",
            parent_count=1,
            child_count=2,
            status="verified",
        )
    )

    assert stored.chunk_bundle_id == "chunk-bundle-abc"
    assert any(
        "DELETE FROM embedding_bundles" in statement
        for statement in connection.cursor_obj.statements
    )
    assert any(
        "UPDATE embedding_runs" in statement
        for statement in connection.cursor_obj.statements
    )
    assert any(
        "DELETE FROM chunk_bundles" in statement
        for statement in connection.cursor_obj.statements
    )


class ChunkBundleRecordingConnection:
    def __init__(self, *, fetchone_results: list[dict[str, object] | None]) -> None:
        self.cursor_obj = ChunkBundleRecordingCursor(fetchone_results=fetchone_results)

    def cursor(self) -> "ChunkBundleRecordingCursor":
        return self.cursor_obj


class ChunkBundleRecordingCursor:
    def __init__(self, *, fetchone_results: list[dict[str, object] | None]) -> None:
        self.statements: list[str] = []
        self.params: list[tuple[object, ...]] = []
        self._fetchone_results = fetchone_results

    def __enter__(self) -> "ChunkBundleRecordingCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, statement: str, params: tuple[object, ...]) -> None:
        self.statements.append(statement)
        self.params.append(params)

    def fetchone(self) -> dict[str, object] | None:
        if not self._fetchone_results:
            return None
        return self._fetchone_results.pop(0)


def test_ensure_registered_persiste_variant_provenance() -> None:
    # Task 6: la provenance de variante viaja al INSERT de chunk_bundles y vuelve en
    # el read-back, sin ser identidad (nullable, par atómico).
    stored_row = {
        "chunk_bundle_id": "chunk-bundle-var",
        "project_id": "proj_alpha",
        "bundle_fingerprint": "chunk-bundle-var",
        "profile_id": "local-structural-v1",
        "profile_fingerprint": "chunking-profile-var",
        "corpus_version": "platform",
        "source_document_id": "doc_1",
        "artifact_relpath": "unit/example.chunking_metadata.json",
        "parent_count": 1,
        "child_count": 2,
        "status": "verified",
        "rag_variant_id": "ragv_local_bge",
        "semantic_recipe_fingerprint": "b" * 64,
    }
    connection = ChunkBundleRecordingConnection(fetchone_results=[None, stored_row])
    repository = PostgresChunkBundleRepository(connection)

    stored = repository.ensure_registered(
        ChunkBundleRef(
            chunk_bundle_id="chunk-bundle-var",
            project_id="proj_alpha",
            bundle_fingerprint="chunk-bundle-var",
            profile_id="local-structural-v1",
            profile_fingerprint="chunking-profile-var",
            corpus_version="platform",
            source_document_id="doc_1",
            artifact_relpath="unit/example.chunking_metadata.json",
            parent_count=1,
            child_count=2,
            status="verified",
            rag_variant_id="ragv_local_bge",
            semantic_recipe_fingerprint="b" * 64,
        )
    )

    insert_idx = next(
        index
        for index, statement in enumerate(connection.cursor_obj.statements)
        if "INSERT INTO chunk_bundles" in statement
    )
    assert "rag_variant_id" in connection.cursor_obj.statements[insert_idx]
    assert "ragv_local_bge" in connection.cursor_obj.params[insert_idx]
    assert ("b" * 64) in connection.cursor_obj.params[insert_idx]
    # project_id también se persiste (antes se caía del INSERT).
    assert "proj_alpha" in connection.cursor_obj.params[insert_idx]
    assert stored.rag_variant_id == "ragv_local_bge"
