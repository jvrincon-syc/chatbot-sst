from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from pydantic import BaseModel


def dump_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, BaseModel):
        data = payload.model_dump(mode="json")
    elif isinstance(payload, list):
        data = [item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in payload]
    else:
        data = payload
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_inventory(path: Path, records: Iterable[BaseModel]) -> None:
    dump_json(path, list(records))


def write_review_list(path: Path, documents: List[dict]) -> None:
    dump_json(path, {"schema_version": "1.0", "documents": documents})
