from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from ingestion.infrastructure.llama_cloud.classify_rules import classification_labels


@dataclass(frozen=True)
class LlamaClassifyConfig:
    mode: str = "FAST"
    language: str = "es"
    max_pages: int = 5

    def to_run_configuration(
        self,
        *,
        labels: tuple[str, ...],
        descriptions: dict[str, list[str]] | None = None,
    ) -> dict[str, object]:
        descriptions = descriptions or classification_labels()
        return {
            "mode": self.mode,
            "rules": [
                {"type": label, "description": _rule_description(label, descriptions)}
                for label in labels
            ],
            "parsing_configuration": {
                "lang": self.language,
                "max_pages": self.max_pages,
            },
        }

    def configuration_hash(self, *, labels: tuple[str, ...]) -> str:
        payload = self.to_run_configuration(labels=labels)
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _rule_description(label: str, descriptions: dict[str, list[str]]) -> str:
    configured = descriptions.get(label, [])
    if configured:
        return configured[0]
    return f"Documento clasificado como {label} segun reglas corporativas SST."
