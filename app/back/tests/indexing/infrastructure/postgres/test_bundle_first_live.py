"""Bundle-first end to end against a real PostgreSQL + pgvector database.

What is real here: every repository is the PostgreSQL adapter, the vectors land
in a real ``idx_vec_*`` table with a real ``vector`` column, activation runs
``activate_bundle``, and retrieval issues a real pgvector ``<=>`` query.

What is not real here: the embedding engine is the deterministic ``mock``
provider, because ``BAAI/bge-m3`` has no usable runtime on this platform (see
the handoff). The engine is the only fake in this test.

Everything runs inside one transaction that is rolled back, so the audited
database is left byte-identical.
"""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from embedding.application.bundle_builder import (
    EmbeddingBundleBuilder,
    EmbeddingBundleValidator,
)
from embedding.application.engine_registry import DefaultEmbeddingEngineRegistry
from embedding.application.profile_verification import (
    ProfileVerificationRequest,
    VerifyEmbeddingProfileCompatibilityUseCase,
)
from embedding.application.run_service import (
    CreateEmbeddingRunRequest,
    CreateEmbeddingRunUseCase,
    EmbeddingRunExecutor,
)
from embedding.infrastructure.filesystem.artifact_store import (
    FilesystemEmbeddingBundleArtifactStore,
)
from embedding.infrastructure.filesystem.chunk_bundle_reader import (
    FilesystemChunkBundleContentReader,
)
from embedding.infrastructure.postgres.repositories import (
    PostgresChunkBundleRepository,
    PostgresEmbeddingBundleRepository,
    PostgresEmbeddingProfileRepository,
    PostgresEmbeddingRunRepository,
    PostgresIndexingTargetRepository,
    PostgresReadinessCheckRepository,
)
from indexing.application.bundle_first.activation import (
    ActivateIndexedBundleUseCase,
    ActivationRequest,
)
from indexing.application.bundle_first.index_bundle import (
    CreateIndexingRunRequest,
    CreateIndexingRunUseCase,
    IndexEmbeddingBundleUseCase,
    IndexingRunExecutor,
)
from indexing.infrastructure.postgres.bundle_first import (
    PostgresIndexingNodeWriter,
    PostgresIndexingRunDocumentRepository,
    PostgresIndexingRunRepository,
)
from indexing.infrastructure.postgres.vector_repository import PostgresVectorRepository
from retrieval.application.query_embedding_service import QueryEmbeddingService
from retrieval.application.retrieval_service import RetrievalSearchService
from retrieval.infrastructure.postgres.repositories import (
    PostgresLexicalSearch,
    PostgresParentExpansion,
    PostgresRetrievalProfileRepository,
    PostgresVectorSearch,
)

pytestmark = pytest.mark.postgres_live

#: Mock/384 lane: a real vector table whose dimension the mock engine can fill.
LIVE_PROFILE_ID = "llama-first-local-v1"
LIVE_VECTOR_TABLE = "idx_vec_llama_first_local_v1"
MOCK_REVISION = "deterministic-v1"
CORPUS_VERSION = "phase1-live-e2e"
DOCUMENT_ID = "doc_live_e2e_probe"
SOURCE_HASH = sha256(b"live-e2e-probe").hexdigest()
SCOPE_TYPE = "chatbot"
SCOPE_ID = "live-e2e-probe"


class _NoopTransactions:
    """Keep every write inside the single outer transaction under test."""

    def transaction(self):
        from contextlib import nullcontext

        return nullcontext()


def _write_chunk_artifacts(chunks_root: Path, *, child_count: int = 4) -> tuple[str, str]:
    base = chunks_root / "live" / "probe"
    base.parent.mkdir(parents=True, exist_ok=True)
    parent_id = "parent-" + sha256(b"live-parent").hexdigest()
    parents = [
        {
            "chunk_id": parent_id,
            "document_id": DOCUMENT_ID,
            "profile_id": "local-structural-v1",
            "ordinal": 0,
            "text": "Politica de seguridad y salud en el trabajo.",
            "source_span": {"page_start": 1, "page_end": 1, "char_start": 0, "char_end": 44},
            "block_ids": ["block-live-1"],
        }
    ]
    children = [
        {
            "chunk_id": "child-" + sha256(f"live-child-{index}".encode()).hexdigest(),
            "parent_id": parent_id,
            "document_id": DOCUMENT_ID,
            "profile_id": "local-structural-v1",
            "ordinal": index,
            "context_prefix": "Politica SST",
            "text": f"Regla numero {index} sobre elementos de proteccion personal.",
            "source_span": {
                "page_start": 1,
                "page_end": 1,
                "char_start": index * 12,
                "char_end": index * 12 + 11,
            },
            "token_count": 10,
        }
        for index in range(child_count)
    ]
    for suffix, rows in (("parent_chunks", parents), ("child_chunks", children)):
        with Path(f"{base}.{suffix}.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    bundle_fingerprint = "chunk-bundle-" + sha256(b"live-bundle").hexdigest()
    Path(f"{base}.chunking_metadata.json").write_text(
        json.dumps(
            {
                "bundle_fingerprint": bundle_fingerprint,
                "child_count": len(children),
                "corpus_version": CORPUS_VERSION,
                "document_id": DOCUMENT_ID,
                "normalized_relpath": "live/probe.md",
                "parent_count": len(parents),
                "profile_fingerprint": "chunking-profile-" + sha256(b"live-profile").hexdigest(),
                "profile_id": "local-structural-v1",
                "source_hash": SOURCE_HASH,
                "source_relpath": "live/probe.md",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return bundle_fingerprint, "live/probe.chunking_metadata.json"


def _seed_document_and_bundle(cursor, *, bundle_fingerprint: str, artifact_relpath: str) -> None:
    cursor.execute(
        """
        INSERT INTO indexing_normalized_documents (
            document_id, source_relpath, source_hash, ingestion_origin, corpus_version,
            processing_status, review_status, markdown_relpath, metadata_relpath,
            pages_relpath, tables_relpath, forms_relpath, artifact_fingerprint, metadata
        )
        VALUES (%s, %s, %s, 'local', %s, 'processed', 'approved', %s, %s, %s, %s, %s, %s, '{}'::jsonb)
        ON CONFLICT (document_id) DO NOTHING
        """,
        (
            DOCUMENT_ID,
            "live/probe.md",
            SOURCE_HASH,
            CORPUS_VERSION,
            "live/probe.md",
            "live/probe.metadata.json",
            "live/probe.pages.json",
            "live/probe.tables.json",
            "live/probe.forms.json",
            bundle_fingerprint,
        ),
    )
    cursor.execute(
        """
        INSERT INTO chunk_bundles (
            chunk_bundle_id, bundle_fingerprint, profile_id, profile_fingerprint,
            corpus_version, source_document_id, artifact_relpath, parent_count,
            child_count, status
        )
        VALUES (%s, %s, 'local-structural-v1', %s, %s, %s, %s, 1, 4, 'legacy_unverified')
        ON CONFLICT (chunk_bundle_id) DO NOTHING
        """,
        (
            bundle_fingerprint,
            bundle_fingerprint,
            "chunking-profile-" + sha256(b"live-profile").hexdigest(),
            CORPUS_VERSION,
            DOCUMENT_ID,
            artifact_relpath,
        ),
    )


def test_bundle_first_e2e_sobre_postgresql_y_pgvector_reales(tmp_path: Path) -> None:
    if not os.environ.get("SST_POSTGRES_DSN"):
        pytest.skip("SST_POSTGRES_DSN is required for live PostgreSQL checks")
    psycopg2 = pytest.importorskip("psycopg2")
    from psycopg2.extras import RealDictCursor

    chunks_root = tmp_path / "chunks"
    bundle_fingerprint, artifact_relpath = _write_chunk_artifacts(chunks_root)

    connection = psycopg2.connect(
        os.environ["SST_POSTGRES_DSN"],
        cursor_factory=RealDictCursor,
    )
    connection.autocommit = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            row = cursor.fetchone()
            assert row is not None, "pgvector extension is not installed"
            _seed_document_and_bundle(
                cursor,
                bundle_fingerprint=bundle_fingerprint,
                artifact_relpath=artifact_relpath,
            )
            # The operator declares the revision on the durable profile; the
            # verification use case then proves it against the live engine.
            cursor.execute(
                "UPDATE indexing_profiles SET model_revision = %s, normalization = 'none'"
                " WHERE profile_id = %s",
                (MOCK_REVISION, LIVE_PROFILE_ID),
            )

        profiles = PostgresEmbeddingProfileRepository(connection)
        targets = PostgresIndexingTargetRepository(connection)
        chunk_bundles = PostgresChunkBundleRepository(connection)
        runs = PostgresEmbeddingRunRepository(connection)
        bundles = PostgresEmbeddingBundleRepository(connection)
        checks = PostgresReadinessCheckRepository(connection)
        registry = DefaultEmbeddingEngineRegistry(environ={}, allow_mock=True)
        artifacts = FilesystemEmbeddingBundleArtifactStore(root=tmp_path / "embeddings")
        content_reader = FilesystemChunkBundleContentReader(chunks_root=chunks_root)

        verification = VerifyEmbeddingProfileCompatibilityUseCase(
            profiles=profiles,
            registry=registry,
            targets=targets,
            readiness_checks=checks,
        ).execute(ProfileVerificationRequest(profile_id=LIVE_PROFILE_ID))
        assert verification.passed is True, [
            check.model_dump() for check in verification.failures()
        ]
        assert verification.revision_source == "engine_observed"

        # The dedicated check kind added by 20260805_16 must be accepted by the
        # real constraint.
        stored_check = checks.latest(
            check_kind="embedding_profile_verification",
            subject_id=LIVE_PROFILE_ID,
        )
        assert stored_check is not None
        assert stored_check.status == "passed"

        builder = EmbeddingBundleBuilder(
            bundles=bundles,
            artifacts=artifacts,
            validator=EmbeddingBundleValidator(artifacts=artifacts),
            readiness_checks=checks,
        )
        embedding_run = CreateEmbeddingRunUseCase(
            runs=runs,
            profiles=profiles,
            chunk_bundles=chunk_bundles,
            registry=registry,
        ).execute(
            request=CreateEmbeddingRunRequest(
                chunk_bundle_id=bundle_fingerprint,
                profile_id=LIVE_PROFILE_ID,
            ),
            idempotency_key="live-e2e-embed",
        )
        completed = EmbeddingRunExecutor(
            runs=runs,
            profiles=profiles,
            chunk_bundles=chunk_bundles,
            bundles=bundles,
            registry=registry,
            builder=builder,
            content_reader=content_reader,
        ).execute(embedding_run.embedding_run_id)
        assert completed.status == "completed", completed.error_summary
        embedding_bundle_id = str(completed.produced_embedding_bundle_id)

        run_documents = PostgresIndexingRunDocumentRepository(connection)
        vectors = PostgresVectorRepository(connection)
        index_use_case = IndexEmbeddingBundleUseCase(
            profiles=profiles,
            chunk_bundles=chunk_bundles,
            bundles=bundles,
            targets=targets,
            nodes=PostgresIndexingNodeWriter(connection),
            vectors=vectors,
            artifacts=artifacts,
            content_reader=content_reader,
            run_documents=run_documents,
            readiness_checks=checks,
            transactions=_NoopTransactions(),
        )
        indexing_runs = PostgresIndexingRunRepository(connection)
        indexing_run = CreateIndexingRunUseCase(
            runs=indexing_runs,
            bundles=bundles,
            profiles=profiles,
            index_use_case=index_use_case,
        ).execute(
            request=CreateIndexingRunRequest(embedding_bundle_id=embedding_bundle_id),
            idempotency_key="live-e2e-index",
        )
        indexed = IndexingRunExecutor(
            runs=indexing_runs,
            index_use_case=index_use_case,
        ).execute(indexing_run.run_id)
        assert indexed.status == "completed", indexed.warnings
        assert indexed.summary["vector_rows"] == 4

        # Real rows, still inactive: indexing never activates.
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(*) AS total FROM {LIVE_VECTOR_TABLE}"
                " WHERE embedding_bundle_id = %s AND is_active = true",
                (embedding_bundle_id,),
            )
            assert cursor.fetchone()["total"] == 0

        retrieval_profiles = PostgresRetrievalProfileRepository(connection)
        activation = ActivateIndexedBundleUseCase(
            runs=indexing_runs,
            bundles=bundles,
            profiles=profiles,
            targets=targets,
            vectors=vectors,
            artifacts=artifacts,
            retrieval_profiles=retrieval_profiles,
            readiness_checks=checks,
            transactions=_NoopTransactions(),
        ).execute(
            ActivationRequest(
                run_id=indexed.run_id,
                consumer_scope_type=SCOPE_TYPE,
                consumer_scope_id=SCOPE_ID,
            )
        )
        assert activation.activated_rows == 4

        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(*) AS total, count(embedding) AS with_vector"
                f"  FROM {LIVE_VECTOR_TABLE}"
                " WHERE embedding_bundle_id = %s AND is_active = true",
                (embedding_bundle_id,),
            )
            row = cursor.fetchone()
            assert row["total"] == 4
            assert row["with_vector"] == 4
            # Prove the column really is a pgvector column.
            cursor.execute(
                """
                SELECT format_type(a.atttypid, a.atttypmod) AS column_type
                  FROM pg_attribute a
                 WHERE a.attrelid = %s::regclass AND a.attname = 'embedding'
                """,
                (LIVE_VECTOR_TABLE,),
            )
            assert cursor.fetchone()["column_type"] == "vector(384)"

        profile = profiles.get(LIVE_PROFILE_ID)
        query_embedding = QueryEmbeddingService(profiles=profiles, registry=registry)
        search = RetrievalSearchService(
            retrieval_profiles=retrieval_profiles,
            profiles=profiles,
            targets=targets,
            query_embedding=query_embedding,
            vector_search=PostgresVectorSearch(connection),
            lexical_search=PostgresLexicalSearch(
                connection,
                embedding_profile_id=profile.profile_id,
            ),
            parent_expansion=PostgresParentExpansion(
                connection,
                embedding_profile_id=profile.profile_id,
            ),
        )
        evidence = search.search(
            retrieval_profile=retrieval_profiles.get(activation.retrieval_profile_id),
            query="elementos de proteccion personal",
            top_k=3,
        )

        assert evidence, "real pgvector query returned no evidence"
        child = evidence[0]
        assert child.source == "vector"
        assert child.embedding_profile_id == LIVE_PROFILE_ID
        assert child.corpus_version == CORPUS_VERSION
        assert child.embedding_bundle_id == embedding_bundle_id
        assert child.document_id == DOCUMENT_ID
        assert child.page_start == 1
        assert child.parent_node_id is not None
        assert any(item.node_id == child.parent_node_id for item in evidence)
    finally:
        connection.rollback()
        connection.close()
