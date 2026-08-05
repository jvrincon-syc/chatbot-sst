from __future__ import annotations

from indexing.domain.profiles import ResolvedIndexingProfile


_DISTANCE_OPS = {
    "cosine": "vector_cosine_ops",
    "l2": "vector_l2_ops",
    "inner_product": "vector_ip_ops",
}


def create_vector_table_sql(profile: ResolvedIndexingProfile) -> str:
    """Build DDL for one validated profile-specific vector table."""

    table = profile.vector_table
    ops = _DISTANCE_OPS[profile.distance_metric]
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    node_id TEXT PRIMARY KEY REFERENCES indexing_nodes(node_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    embedding vector({profile.embedding_dimension}) NOT NULL,
    metadata JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS {table}_document_id
    ON {table} (document_id);

CREATE INDEX IF NOT EXISTS {table}_metadata
    ON {table} USING gin (metadata);

CREATE INDEX IF NOT EXISTS {table}_hnsw
    ON {table} USING hnsw (embedding {ops});
""".strip()
