from __future__ import annotations

from typing import Protocol

from ingestion.domain.models.provider import ProviderJobRef


class ProviderRunRepository(Protocol):
    def save(self, job_ref: ProviderJobRef) -> None: ...

    def get(self, provider: str, capability: str, job_id: str) -> ProviderJobRef | None: ...
