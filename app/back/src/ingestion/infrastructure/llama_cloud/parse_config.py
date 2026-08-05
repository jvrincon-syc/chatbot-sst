from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ingestion.config.llama_settings import LlamaSettings, ParseExpand, ParseTier


@dataclass(frozen=True)
class LlamaParseConfig:
    tier: ParseTier = "cost_effective"
    version: str = "latest"
    expand: tuple[ParseExpand, ...] = ("markdown", "items", "metadata", "job_metadata")
    ocr_languages: tuple[str, ...] = ("es",)
    timeout_seconds: int = 900

    @classmethod
    def from_settings(cls, settings: LlamaSettings) -> "LlamaParseConfig":
        return cls(
            tier=settings.parse_tier,
            version=settings.parse_version,
            expand=settings.parse_expand,
            ocr_languages=settings.parse_ocr_languages,
            timeout_seconds=settings.parse_timeout_seconds,
        )

    def to_parse_kwargs(self) -> dict[str, object]:
        return {
            "tier": self.tier,
            "version": self.version,
            "expand": list(self.effective_expand()),
            "processing_options": {
                "ocr_parameters": {"languages": list(self.ocr_languages)}
            },
            "processing_control": {
                "timeouts": {"base_in_seconds": self.timeout_seconds}
            },
        }

    def effective_expand(self) -> tuple[ParseExpand, ...]:
        if self.tier != "fast":
            return self.expand
        allowed = {"text", "text_full", "metadata", "job_metadata"}
        filtered = tuple(value for value in self.expand if value in allowed)
        return filtered or ("text", "metadata", "job_metadata")

    def configuration_hash(self) -> str:
        payload = {
            "tier": self.tier,
            "version": self.version,
            "expand": list(self.effective_expand()),
            "ocr_languages": list(self.ocr_languages),
            "timeout_seconds": self.timeout_seconds,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()
