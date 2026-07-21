from __future__ import annotations


def recall_at_k(
    ranked_results: list[list[str]],
    relevant_ids: list[set[str]],
    *,
    k: int,
) -> float:
    if not ranked_results:
        return 0.0
    hits = 0
    for ranked, relevant in zip(ranked_results, relevant_ids):
        hits += bool(set(ranked[:k]) & relevant)
    return hits / len(ranked_results)


def mean_reciprocal_rank(
    ranked_results: list[list[str]],
    relevant_ids: list[set[str]],
) -> float:
    if not ranked_results:
        return 0.0
    total = 0.0
    for ranked, relevant in zip(ranked_results, relevant_ids):
        for index, node_id in enumerate(ranked, start=1):
            if node_id in relevant:
                total += 1 / index
                break
    return total / len(ranked_results)
