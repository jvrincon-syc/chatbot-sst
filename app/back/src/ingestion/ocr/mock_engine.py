from __future__ import annotations

from pathlib import Path
from typing import Dict, List


class MockOcrEngine:
    engine = "mock"
    engine_version = "0"
    language = "spa"

    def __init__(self, pages: List[Dict]) -> None:
        self._pages = pages

    def extract_pages(self, source_path: Path) -> List[Dict]:
        return list(self._pages)
