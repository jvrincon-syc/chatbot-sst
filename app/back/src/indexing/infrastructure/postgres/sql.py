from __future__ import annotations

from indexing.domain.bundle_first import IndexingTarget
from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.llama_index.pgvector_store import VectorStoreWriteError
from psycopg2 import sql


_DISTANCE_OPS = {
    "cosine": "vector_cosine_ops",
    "l2": "vector_l2_ops",
    "inner_product": "vector_ip_ops",
}


def create_vector_table_sql(
    *,
    profile: ResolvedIndexingProfile,
    target: IndexingTarget,
) -> sql.Composed:
    """Build DDL for one validated, catalog-authoritative vector table."""

    if target.vector_table != profile.vector_table:
        raise VectorStoreWriteError("indexing target/catalog table mismatch")
    ops = _DISTANCE_OPS[profile.distance_metric]
    table_identifier = sql.Identifier(target.postgres_schema, target.vector_table)
    document_index = sql.Identifier(f"{target.vector_table}_document_id")
    metadata_index = sql.Identifier(f"{target.vector_table}_metadata")
    hnsw_index = sql.Identifier(f"{target.vector_table}_hnsw")
    return sql.SQL(
        """
CREATE TABLE IF NOT EXISTS {} (
    node_id TEXT PRIMARY KEY REFERENCES indexing_nodes(node_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    embedding vector({}) NOT NULL,
    metadata JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS {}
    ON {} (document_id);

CREATE INDEX IF NOT EXISTS {}
    ON {} USING gin (metadata);

CREATE INDEX IF NOT EXISTS {}
    ON {} USING hnsw (embedding {});
""".strip()
    ).format(
        table_identifier,
        sql.SQL(str(profile.embedding_dimension)),
        document_index,
        table_identifier,
        metadata_index,
        table_identifier,
        hnsw_index,
        table_identifier,
        sql.SQL(ops),
    )
