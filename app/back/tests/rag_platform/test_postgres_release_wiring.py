from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rag_platform.domain.errors import CorpusSnapshotNotFound, RagVariantNotFound
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    CorpusOrganizationPolicy,
    EligibilityDecision,
    compute_project_configuration_fingerprint,
)
from rag_platform.infrastructure.postgres.document_repositories import (
    PostgresCorpusSnapshotRepository,
)
from rag_platform.infrastructure.postgres.project_repositories import (
    PostgresProjectConfigurationFingerprintReader,
    PostgresRagVariantRepository,
)


def test_postgres_rag_variant_repository_get_lee_por_id() -> None:
    connection = RecordingConnection(
        [{"fetchone": _variant_row("ragv_bge", "proj_alpha")}]
    )

    variant = PostgresRagVariantRepository(connection).get(
        PlatformId(IdentityKind.RAG_VARIANT, "ragv_bge")
    )

    assert variant.rag_variant_id.value == "ragv_bge"
    assert variant.project_id.value == "proj_alpha"
    assert "WHERE rag_variant_id = %s" in connection.cursor_obj.statements[0]
    assert connection.cursor_obj.params[0] == ("ragv_bge",)


def test_postgres_rag_variant_repository_get_falla_si_no_existe() -> None:
    repository = PostgresRagVariantRepository(
        RecordingConnection([{"fetchone": None}])
    )

    with pytest.raises(RagVariantNotFound):
        repository.get(PlatformId(IdentityKind.RAG_VARIANT, "ragv_missing"))


def test_postgres_corpus_snapshot_repository_get_lee_snapshot_y_membresias() -> None:
    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    connection = RecordingConnection(
        [
            {
                "fetchone": (
                    "corpus_s1",
                    "proj_alpha",
                    "a" * 64,
                    2,
                    now,
                )
            },
            {
                "fetchall": [
                    (0, "srev_000", EligibilityDecision.NOT_REQUIRED.value),
                    (1, "srev_001", EligibilityDecision.OPERATOR_WAIVER.value),
                ]
            },
        ]
    )

    snapshot = PostgresCorpusSnapshotRepository(connection).get(
        PlatformId(IdentityKind.CORPUS_SNAPSHOT, "corpus_s1")
    )

    assert snapshot.corpus_snapshot_id.value == "corpus_s1"
    assert snapshot.project_id.value == "proj_alpha"
    assert [doc.source_document_revision_id.value for doc in snapshot.documents] == [
        "srev_000",
        "srev_001",
    ]
    assert "WHERE corpus_snapshot_id = %s" in connection.cursor_obj.statements[0]
    assert connection.cursor_obj.params[0] == ("corpus_s1",)


def test_postgres_corpus_snapshot_repository_get_falla_si_no_existe() -> None:
    repository = PostgresCorpusSnapshotRepository(
        RecordingConnection([{"fetchone": None}])
    )

    with pytest.raises(CorpusSnapshotNotFound):
        repository.get(PlatformId(IdentityKind.CORPUS_SNAPSHOT, "corpus_missing"))


def test_postgres_project_configuration_fingerprint_reader_reconstruye_fingerprint() -> None:
    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    connection = RecordingConnection(
        [
            {"fetchone": (3, CorpusOrganizationPolicy.HYBRID_V1.value, now)},
            {
                "fetchall": [
                    ("politica", "Politica SST", "sst"),
                    ("procedimiento", "Procedimiento", "generic"),
                ]
            },
            {
                "fetchall": [
                    ("bge-m3", True),
                    ("voyage-4", False),
                ]
            },
            {
                "fetchall": [
                    ("primary", "it_bge", "bge-m3"),
                    ("secondary", "it_voyage", "voyage-4"),
                ]
            },
        ]
    )

    fingerprint = PostgresProjectConfigurationFingerprintReader(connection).configuration_fingerprint(
        PlatformId(IdentityKind.PROJECT, "proj_alpha")
    )

    assert fingerprint == compute_project_configuration_fingerprint(
        version=3,
        corpus_organization_policy=CorpusOrganizationPolicy.HYBRID_V1,
        document_types=(
            ("politica", "Politica SST", "sst"),
            ("procedimiento", "Procedimiento", "generic"),
        ),
        embedding_profiles=(("bge-m3", True), ("voyage-4", False)),
        target_bindings=(
            ("primary", "it_bge", "bge-m3"),
            ("secondary", "it_voyage", "voyage-4"),
        ),
    )


def test_postgres_sealed_chunk_bundle_repository_actualiza_fila_existente_con_metadatos_de_plataforma() -> None:
    from embedding.domain.models import ChunkBundleRef
    from rag_platform.infrastructure.postgres.artifact_repositories import (
        PostgresSealedChunkBundleRepository,
    )

    connection = RecordingConnection([{}])
    repository = PostgresSealedChunkBundleRepository(connection)

    repository.register_sealed_bundle(
        ChunkBundleRef(
            chunk_bundle_id="chunk-bundle-1",
            project_id="proj_alpha",
            bundle_fingerprint="fingerprint-1",
            profile_id="local-structural-v1",
            profile_fingerprint="chunking-profile-1",
            corpus_version="corpus-v1",
            source_document_id="doc_001",
            artifact_relpath="unit/example.chunking_metadata.json",
            parent_count=1,
            child_count=2,
            status="verified",
        ),
        project_id=PlatformId(IdentityKind.PROJECT, "proj_alpha"),
        normalized_document_id="ndoc_alpha",
        chunking_profile_fingerprint="a" * 64,
        bundle_schema_version="sealed-v1",
    )

    statement = connection.cursor_obj.statements[0]
    params = connection.cursor_obj.params[0]

    assert "ON CONFLICT (chunk_bundle_id) DO UPDATE SET" in statement
    assert "project_id = EXCLUDED.project_id" in statement
    assert "normalized_document_id = EXCLUDED.normalized_document_id" in statement
    assert params[0] == "chunk-bundle-1"
    assert params[10] == "proj_alpha"
    assert params[11] == "ndoc_alpha"


def _variant_row(variant_id: str, project_id: str) -> tuple[object, ...]:
    return (
        variant_id,
        project_id,
        "pp_local",
        "cp_struct",
        "bge-m3",
        "a" * 64,
        "active",
        datetime(2026, 8, 12, tzinfo=timezone.utc),
    )


class RecordingConnection:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.cursor_obj = RecordingCursor(responses)

    def cursor(self) -> RecordingCursor:
        return self.cursor_obj


class RecordingCursor:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self._responses = list(responses)
        self._current: dict[str, object] = {}
        self.statements: list[str] = []
        self.params: list[tuple[object, ...]] = []

    def __enter__(self) -> RecordingCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, statement: str, params: tuple[object, ...]) -> None:
        self.statements.append(statement)
        self.params.append(params)
        self._current = self._responses.pop(0) if self._responses else {}

    def fetchone(self):
        return self._current.get("fetchone")

    def fetchall(self):
        return self._current.get("fetchall", [])
