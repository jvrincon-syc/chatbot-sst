from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_package_json_declares_indexing_scripts() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["indexing:run"] == (
        "npm run python -- scripts/indexing/run_indexing.py"
    )
    assert package["scripts"]["indexing:validate"] == (
        "npm run python -- scripts/indexing/validate_index.py"
    )
    assert package["scripts"]["test:indexing"] == (
        "npm run python -- -m pytest app/back/tests/indexing"
    )
