from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LlamaExtractConfig:
    schema_name: str
    critical_fields: tuple[str, ...] = ()
    data_schema: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    tier: str = "cost_effective"
    parse_tier: str = "fast"
    version: str = "latest"
    max_pages: int = 5
    cite_sources: bool = True
    confidence_scores: bool = True

    def to_run_configuration(self) -> dict[str, object]:
        return {
            "data_schema": self.data_schema,
            "tier": self.tier,
            "parse_tier": self.parse_tier,
            "version": self.version,
            "max_pages": self.max_pages,
            "cite_sources": self.cite_sources,
            "confidence_scores": self.confidence_scores,
        }
