from __future__ import annotations

import json

from ingestion.infrastructure.llama_cloud.raw_result_store import RawResultStore


def test_raw_result_store_writes_sanitized_provider_payload(tmp_path) -> None:
    store = RawResultStore(tmp_path)

    path = store.save(
        document_id="doc_123",
        configuration_hash="sha256:config",
        capability="parse",
        payload={"id": "job_123", "api_key": "llx-secret", "nested": {"url": "https://signed.example"}},
    )

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["id"] == "job_123"
    assert saved["api_key"] == "***redacted***"
    assert saved["nested"]["url"] == "***redacted***"
    assert "doc_123" in path.as_posix()
