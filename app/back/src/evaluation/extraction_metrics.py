from __future__ import annotations

from typing import Any


def exact_match_rate(*, expected: dict[str, Any], actual: dict[str, Any]) -> float:
    if not expected:
        return 0.0
    matches = sum(1 for key, value in expected.items() if actual.get(key) == value)
    return matches / len(expected)
