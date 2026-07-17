from __future__ import annotations

import hashlib
import json
from typing import Any


ROOT_KEYS = {"docs_raw", "docs_normalized", "staging_root", "live_root", "candidate_root"}
SECRET_MARKERS = ("secret", "token", "password", "key")


def processing_fingerprint(config: dict[str, Any], capability_versions: dict[str, Any]) -> str:
    payload = {
        "config": _portable(config),
        "capability_versions": _portable(capability_versions),
    }
    return _digest(payload)


def validation_fingerprint(validator_version: str, golden_hash: str) -> str:
    return _digest({"validator_version": validator_version, "golden_hash": golden_hash})


def _portable(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _portable(child)
            for key, child in sorted(value.items())
            if key not in ROOT_KEYS and not _secret_key(key)
        }
    if isinstance(value, (list, tuple)):
        return [_portable(child) for child in value]
    return value


def _secret_key(key: str) -> bool:
    folded = key.casefold()
    return any(marker in folded for marker in SECRET_MARKERS)


def _digest(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
