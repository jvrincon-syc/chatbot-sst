from __future__ import annotations

import json
from pathlib import Path

from ingestion.domain.models.provider import ProviderJobRef


class JsonlProviderRunRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    def save(self, job_ref: ProviderJobRef) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = job_ref.model_dump(mode="json")
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    def get(self, provider: str, capability: str, job_id: str) -> ProviderJobRef | None:
        if not self._path.exists():
            return None
        matched: ProviderJobRef | None = None
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            job = ProviderJobRef.model_validate(json.loads(line))
            if (
                job.provider == provider
                and job.capability == capability
                and job.job_id == job_id
            ):
                matched = job
        return matched
