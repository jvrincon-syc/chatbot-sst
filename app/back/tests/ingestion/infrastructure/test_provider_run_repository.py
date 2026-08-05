from __future__ import annotations

from datetime import datetime, timezone

from ingestion.domain.models.provider import ProviderJobRef
from ingestion.infrastructure.provider_runs.jsonl_repository import JsonlProviderRunRepository


def test_jsonl_provider_run_repository_saves_and_reads_job_refs(tmp_path) -> None:
    path = tmp_path / "provider_runs.jsonl"
    repository = JsonlProviderRunRepository(path)
    job = ProviderJobRef(
        provider="llama_cloud",
        capability="parse",
        job_id="job_123",
        status="completed",
        configuration_hash="sha256:config",
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        completed_at=datetime(2026, 7, 21, 0, 1, tzinfo=timezone.utc),
    )

    repository.save(job)

    assert repository.get("llama_cloud", "parse", "job_123") == job


def test_jsonl_provider_run_repository_latest_entry_wins(tmp_path) -> None:
    path = tmp_path / "provider_runs.jsonl"
    repository = JsonlProviderRunRepository(path)
    pending = ProviderJobRef(
        provider="llama_cloud",
        capability="parse",
        job_id="job_123",
        status="pending",
        configuration_hash="sha256:config",
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    completed = pending.model_copy(update={"status": "completed"})

    repository.save(pending)
    repository.save(completed)

    assert repository.get("llama_cloud", "parse", "job_123").status == "completed"
