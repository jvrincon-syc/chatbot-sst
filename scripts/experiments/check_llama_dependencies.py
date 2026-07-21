from __future__ import annotations

import importlib
import importlib.metadata
from dataclasses import dataclass, field
from typing import Callable


REQUIRED_DISTRIBUTIONS = {
    "llama-cloud": ("llama_cloud", "2.12.0"),
    "llama-index-core": ("llama_index.core", "0.14.23"),
    "llama-index-vector-stores-postgres": (
        "llama_index.vector_stores.postgres",
        "0.8.1",
    ),
}
UNEXPECTED_DISTRIBUTIONS = ("llama-index",)


@dataclass(frozen=True)
class DependencyCheck:
    ok: bool
    missing: list[str] = field(default_factory=list)
    unexpected: list[str] = field(default_factory=list)
    versions: dict[str, str] = field(default_factory=dict)


def check_installed_packages(
    distributions: dict[str, str | None] | None = None,
    import_module: Callable[[str], object] | None = None,
) -> DependencyCheck:
    versions = distributions if distributions is not None else _installed_versions()
    importer = import_module or importlib.import_module
    found_versions: dict[str, str] = {}
    missing: list[str] = []

    for distribution, (module_name, expected_version) in REQUIRED_DISTRIBUTIONS.items():
        installed = versions.get(distribution)
        if installed != expected_version:
            missing.append(distribution)
            continue
        try:
            importer(module_name)
        except ImportError:
            missing.append(distribution)
            continue
        found_versions[distribution] = installed

    unexpected = [
        distribution
        for distribution in UNEXPECTED_DISTRIBUTIONS
        if versions.get(distribution) is not None
    ]

    return DependencyCheck(
        ok=not missing and not unexpected,
        missing=missing,
        unexpected=unexpected,
        versions=found_versions | _pydantic_version(versions),
    )


def _installed_versions() -> dict[str, str | None]:
    names = tuple(REQUIRED_DISTRIBUTIONS) + UNEXPECTED_DISTRIBUTIONS + ("pydantic",)
    result: dict[str, str | None] = {}
    for name in names:
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def _pydantic_version(versions: dict[str, str | None]) -> dict[str, str]:
    version = versions.get("pydantic")
    return {"pydantic": version} if version is not None else {}


def main() -> int:
    result = check_installed_packages()
    print(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
