from __future__ import annotations

from retrieval.fusion import RetrievedCandidate


def preserve_order_reranker(candidates: list[RetrievedCandidate]) -> list[RetrievedCandidate]:
    return [
        RetrievedCandidate(
            node_id=candidate.node_id,
            text=candidate.text,
            score=candidate.score,
            source=candidate.source,
            metadata={
                **candidate.metadata,
                "original_score": candidate.score,
            },
        )
        for candidate in candidates
    ]


"""Esto se debe ajustar para que primero pase por un faq (banco de preguntas y respuestas) usando 
fuzzy si hay una coincidencia con un porcentaje de similitud considerablemente
alto se manda la respuesta ya ocnfigurada, si no se encuentra pasar a un reranker 
de los"""