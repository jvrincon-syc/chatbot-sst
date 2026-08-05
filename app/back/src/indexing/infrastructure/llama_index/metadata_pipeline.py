from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from llama_index.core.schema import BaseNode


class MetadataEnrichmentPipeline:
    def __init__(
        self,
        *,
        generative_metadata: Mapping[str, Mapping[str, Any]] | None = None,
        generation_version: str | None = None,
    ) -> None:
        self._generative_metadata = generative_metadata or {}
        self._generation_version = generation_version

    def apply(self, nodes: Sequence[BaseNode]) -> list[BaseNode]:
        enriched: list[BaseNode] = []
        for node in nodes:
            update = dict(self._generative_metadata.get(node.id_, {}))
            if update:
                update["generation_version"] = self._generation_version
            enriched.append(
                node.model_copy(
                    update={"metadata": {**node.metadata, **update}},
                    deep=True,
                )
            )
        return enriched
