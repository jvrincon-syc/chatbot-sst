from __future__ import annotations

import json

from ingestion.application.ports.usage_ledger import ProviderUsage
from ingestion.infrastructure.usage.jsonl_ledger import (
    JsonlUsageLedger,
    summarize_usage_ledger,
)


def test_jsonl_usage_ledger_appends_sanitized_usage_entries(tmp_path) -> None:
    path = tmp_path / "usage.jsonl"
    ledger = JsonlUsageLedger(path)

    ledger.record(
        ProviderUsage(
            provider="llama_cloud",
            capability="parse",
            document_id="doc_123",
            credits=4.0,
            elapsed_seconds=12.5,
        )
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["provider"] == "llama_cloud"
    assert payload["credits"] == 4.0
    assert "api_key" not in payload


def test_summarize_usage_ledger_groups_by_provider_and_capability(tmp_path) -> None:
    path = tmp_path / "usage.jsonl"
    ledger = JsonlUsageLedger(path)
    ledger.record(
        ProviderUsage(
            provider="llama_cloud",
            capability="parse",
            document_id="doc_1",
            credits=2.0,
            elapsed_seconds=10.0,
        )
    )
    ledger.record(
        ProviderUsage(
            provider="llama_cloud",
            capability="extract",
            document_id="doc_1",
            credits=3.5,
            elapsed_seconds=8.0,
        )
    )

    summary = summarize_usage_ledger(path)

    assert summary == {
        "total_credits": 5.5,
        "total_elapsed_seconds": 18.0,
        "documents": ["doc_1"],
        "by_capability": {
            "parse": {"credits": 2.0, "elapsed_seconds": 10.0, "count": 1},
            "extract": {"credits": 3.5, "elapsed_seconds": 8.0, "count": 1},
        },
        "by_provider": {
            "llama_cloud": {"credits": 5.5, "elapsed_seconds": 18.0, "count": 2},
        },
    }
