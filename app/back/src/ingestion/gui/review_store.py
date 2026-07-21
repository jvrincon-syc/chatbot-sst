from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReviewDecision:
    document_id: str
    source_relpath: str
    decision: str
    reason: str
    decided_at: str

    def __post_init__(self) -> None:
        if not self.document_id:
            raise ValueError("document_id must not be empty")
        if (
            not self.source_relpath
            or self.source_relpath.startswith("/")
            or ".." in self.source_relpath.split("/")
        ):
            raise ValueError("source_relpath must be a safe relative POSIX path")
        if self.decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        if not self.reason.strip():
            raise ValueError("reason must not be empty")
        if not self.decided_at:
            raise ValueError("decided_at must not be empty")


def load_review_decisions(path: Path) -> list[ReviewDecision]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return [ReviewDecision(**item) for item in items]


def save_review_decision(path: Path, decision: ReviewDecision) -> list[ReviewDecision]:
    decisions = [
        item
        for item in load_review_decisions(path)
        if item.document_id != decision.document_id
    ]
    decisions.append(decision)
    decisions.sort(key=lambda item: item.source_relpath)
    payload = {
        "schema_version": "2.0",
        "generated_at": decision.decided_at,
        "items": [asdict(item) for item in decisions],
    }
    _write_json_atomic(path, payload)
    return decisions


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
