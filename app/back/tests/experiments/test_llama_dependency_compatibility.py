from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

from scripts.experiments.check_llama_dependencies import DependencyCheck, check_installed_packages


ROOT = Path(__file__).resolve().parents[4]


def test_pyproject_declares_granular_llama_optional_dependencies() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    dependencies = pyproject["project"]["dependencies"]
    optional = pyproject["project"]["optional-dependencies"]

    assert "pydantic>=2.11.5,<3" in dependencies
    assert optional["llama-cloud"] == ["llama-cloud==2.12.0"]
    assert optional["llama-indexing"] == [
        "llama-index-core==0.14.23",
        "llama-index-vector-stores-postgres==0.8.1",
    ]


def test_dependency_check_reports_missing_optional_packages_without_importing_sdk_objects() -> None:
    result = check_installed_packages(
        distributions={
            "llama-cloud": "2.12.0",
            "llama-index-core": "0.14.23",
            "llama-index-vector-stores-postgres": "0.8.1",
            "llama-index": None,
        },
        import_module=lambda _name: object(),
    )

    assert result.ok is True
    assert result.missing == []
    assert result.unexpected == []


def test_dependency_check_fails_if_llama_index_metapackage_is_installed() -> None:
    result = check_installed_packages(
        distributions={
            "llama-cloud": "2.12.0",
            "llama-index-core": "0.14.23",
            "llama-index-vector-stores-postgres": "0.8.1",
            "llama-index": "0.14.0",
        },
        import_module=lambda _name: object(),
    )

    assert result == DependencyCheck(
        ok=False,
        missing=[],
        unexpected=["llama-index"],
        versions={
            "llama-cloud": "2.12.0",
            "llama-index-core": "0.14.23",
            "llama-index-vector-stores-postgres": "0.8.1",
        },
    )


def test_dependency_check_can_inspect_real_environment() -> None:
    result = check_installed_packages()

    assert result.versions.get("pydantic") == importlib.metadata.version("pydantic")
