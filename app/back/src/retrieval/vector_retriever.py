from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from retrieval.fusion import RetrievedCandidate


@dataclass(frozen=True)
class VectorCandidate:
    node_id: str
    text: str
    embedding: list[float]
    metadata: dict[str, Any]


class VectorRetriever:
    def __init__(self, *, candidates: list[VectorCandidate]) -> None:
        self._candidates = candidates

    def search(
        self,
        *,
        query_embedding: list[float],
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[RetrievedCandidate]:
        filters = filters or {}
        scored = [
            RetrievedCandidate(
                node_id=candidate.node_id,
                text=candidate.text,
                score=_cosine(query_embedding, candidate.embedding),
                source="vector",
                metadata=dict(candidate.metadata),
            )
            for candidate in self._candidates
            if _matches_filters(candidate.metadata, filters)
        ]
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]


def _matches_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    return all(metadata.get(key) == value for key, value in filters.items())


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions must match")
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)
