from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ingestion.application.ports.usage_ledger import ProviderUsage


class JsonlUsageLedger:
    def __init__(self, path: Path) -> None:
        self._path = path

    def record(self, usage: ProviderUsage) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = usage.model_dump(mode="json")
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def summarize_usage_ledger(path: Path) -> dict[str, Any]:
    by_capability: dict[str, dict[str, float | int]] = {}
    by_provider: dict[str, dict[str, float | int]] = {}
    documents: set[str] = set()
    total_credits = 0.0
    total_elapsed = 0.0
    if not path.exists():
        return {
            "total_credits": 0.0,
            "total_elapsed_seconds": 0.0,
            "documents": [],
            "by_capability": {},
            "by_provider": {},
        }

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        usage = ProviderUsage.model_validate(payload)
        documents.add(usage.document_id)
        total_credits += float(usage.credits)
        total_elapsed += float(usage.elapsed_seconds)
        _add_usage(
            by_capability,
            usage.capability,
            credits=float(usage.credits),
            elapsed_seconds=float(usage.elapsed_seconds),
        )
        _add_usage(
            by_provider,
            usage.provider,
            credits=float(usage.credits),
            elapsed_seconds=float(usage.elapsed_seconds),
        )

    return {
        "total_credits": total_credits,
        "total_elapsed_seconds": total_elapsed,
        "documents": sorted(documents),
        "by_capability": by_capability,
        "by_provider": by_provider,
    }


def write_usage_manifest(*, source_jsonl: Path, target_json: Path) -> dict[str, Any]:
    summary = summarize_usage_ledger(source_jsonl)
    target_json.parent.mkdir(parents=True, exist_ok=True)
    target_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def _add_usage(
    bucket: dict[str, dict[str, float | int]],
    key: str,
    *,
    credits: float,
    elapsed_seconds: float,
) -> None:
    item = bucket.setdefault(
        key,
        {"credits": 0.0, "elapsed_seconds": 0.0, "count": 0},
    )
    item["credits"] = float(item["credits"]) + credits
    item["elapsed_seconds"] = float(item["elapsed_seconds"]) + elapsed_seconds
    item["count"] = int(item["count"]) + 1
