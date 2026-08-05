from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievedCandidate:
    node_id: str
    text: str
    score: float
    source: str
    metadata: dict[str, Any]


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievedCandidate]],
    *,
    k: int = 60,
) -> list[RetrievedCandidate]:
    scores: dict[str, float] = {}
    candidates: dict[str, RetrievedCandidate] = {}
    sources: dict[str, list[str]] = {}
    for ranked in ranked_lists:
        for rank, candidate in enumerate(ranked, start=1):
            scores[candidate.node_id] = scores.get(candidate.node_id, 0.0) + 1.0 / (k + rank)
            candidates.setdefault(candidate.node_id, candidate)
            source_list = sources.setdefault(candidate.node_id, [])
            if candidate.source not in source_list:
                source_list.append(candidate.source)

    fused: list[RetrievedCandidate] = []
    for node_id, candidate in candidates.items():
        metadata = {
            **candidate.metadata,
            "retrieval_sources": sources[node_id],
        }
        fused.append(
            RetrievedCandidate(
                node_id=node_id,
                text=candidate.text,
                score=scores[node_id],
                source="fusion",
                metadata=metadata,
            )
        )
    return sorted(fused, key=lambda item: item.score, reverse=True)
