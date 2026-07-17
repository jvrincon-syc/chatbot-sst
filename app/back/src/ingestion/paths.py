from __future__ import annotations

import hashlib
import os
import posixpath
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Iterable


def canonical_relpath(value: str | os.PathLike[str]) -> str:
    """Return a canonical raw-root-relative POSIX path."""

    raw = os.fspath(value)
    if not raw:
        raise ValueError("relative path must not be empty")
    if "\\" in raw:
        raise ValueError("relative path must use POSIX separators")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ValueError("relative path must not be absolute or drive-qualified")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("relative path contains an unsafe component")
    return raw


def stable_document_id(source_relpath: str | os.PathLike[str]) -> str:
    canonical = canonical_relpath(source_relpath)
    return "doc_" + hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ArtifactPaths:
    source_relpath: str
    normalized_base: str
    markdown: str
    metadata: str
    pages: str
    ocr: str
    tables: str
    forms: str

    @classmethod
    def for_source(cls, source_relpath: str | os.PathLike[str]) -> "ArtifactPaths":
        source = canonical_relpath(source_relpath)
        normalized_base, _ = posixpath.splitext(source)
        return cls(
            source_relpath=source,
            normalized_base=normalized_base,
            markdown=f"{normalized_base}.md",
            metadata=f"{normalized_base}.metadata.json",
            pages=f"{normalized_base}.pages.json",
            ocr=f"{normalized_base}.ocr.json",
            tables=f"{normalized_base}.tables.json",
            forms=f"{normalized_base}.forms.json",
        )

    def required_relpaths(self) -> tuple[str, ...]:
        return (
            self.markdown,
            self.metadata,
            self.pages,
            self.ocr,
            self.tables,
            self.forms,
        )


def preflight_artifact_paths(
    sources: Iterable[str | os.PathLike[str]],
) -> list[ArtifactPaths]:
    paths = [ArtifactPaths.for_source(source) for source in sources]
    owners: dict[str, str] = {}
    for artifact_paths in paths:
        for field in fields(artifact_paths):
            if field.name in {"source_relpath", "normalized_base"}:
                continue
            relpath = getattr(artifact_paths, field.name)
            previous = owners.get(relpath)
            if previous is not None:
                raise ValueError(
                    "artifact path collision between "
                    f"{previous!r} and {artifact_paths.source_relpath!r}: {relpath!r}"
                )
            owners[relpath] = artifact_paths.source_relpath
    return paths
