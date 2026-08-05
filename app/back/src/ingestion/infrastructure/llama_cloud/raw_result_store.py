from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SECRET_KEYS = {"api_key", "token", "authorization", "signed_url", "url"}
SIGNED_URL = re.compile(r"https?://[^\s]+", re.IGNORECASE)


class RawResultStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(
        self,
        *,
        document_id: str,
        configuration_hash: str,
        capability: str,
        payload: dict[str, Any],
    ) -> Path:
        safe_hash = re.sub(r"[^A-Za-z0-9_.-]", "_", configuration_hash)
        target = self._root / document_id / safe_hash / f"{capability}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(_redact(payload), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return target


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***redacted***" if key.lower() in SECRET_KEYS else _redact(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact(child) for child in value]
    if isinstance(value, str) and SIGNED_URL.match(value):
        return "***redacted***"
    return value
