from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionCacheKey:
    document_id: str
    source_hash: str
    profile_id: str
    processing_fingerprint: str


class InMemoryIngestionCache:
    def __init__(self) -> None:
        self._keys: set[IngestionCacheKey] = set()

    def has(self, key: IngestionCacheKey) -> bool:
        return key in self._keys

    def record(self, key: IngestionCacheKey) -> None:
        self._keys.add(key)
