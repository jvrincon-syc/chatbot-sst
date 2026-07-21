from __future__ import annotations

from dataclasses import dataclass

from ingestion.infrastructure.llama_cloud.classify_rules import classification_labels


@dataclass(frozen=True)
class LlamaClassifyConfig:
    mode: str = "FAST"
    language: str = "es"
    max_pages: int = 5

    def to_run_configuration(self, *, labels: tuple[str, ...]) -> dict[str, object]:
        descriptions = classification_labels()
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


def _rule_description(label: str, descriptions: dict[str, list[str]]) -> str:
    configured = descriptions.get(label, [])
    if configured:
        return configured[0]
    return f"Documento clasificado como {label} segun reglas corporativas SST."
