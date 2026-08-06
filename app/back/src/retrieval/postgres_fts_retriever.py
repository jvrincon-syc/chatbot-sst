from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FtsQuery:
    sql: str
    params: dict[str, Any]


class PostgresFtsRetriever:
    """Legacy full-text retriever over ``llama_index_documents``.

    Superseded on the official path by
    ``retrieval.infrastructure.postgres.repositories.PostgresLexicalSearch``,
    which reads ``indexing_nodes`` and honours the corpus and review
    filters. Remove once the legacy retrieval path is retired.
    """

    @staticmethod
    def build_query(filters: dict[str, Any] | None = None) -> FtsQuery:
        filters = filters or {}
        where = ["to_tsvector('spanish', text) @@ plainto_tsquery('spanish', %(query)s)"]
        params: dict[str, Any] = {"query": ""}
        for key, value in filters.items():
            where.append(f"metadata->>'{key}' = %({key})s")
            params[key] = value
        sql = (
            "SELECT node_id, text, metadata, "
            "ts_rank(to_tsvector('spanish', text), plainto_tsquery('spanish', %(query)s)) AS score "
            "FROM llama_index_documents WHERE "
            + " AND ".join(where)
            + " ORDER BY score DESC LIMIT %(limit)s"
        )
        params["limit"] = 10
        return FtsQuery(sql=sql, params=params)
