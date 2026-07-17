from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.paths import (
    ArtifactPaths,
    canonical_relpath,
    preflight_artifact_paths,
    stable_document_id,
)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "/absolute/document.pdf",
        "C:/raw/document.pdf",
        "C:\\raw\\document.pdf",
        "folder\\document.pdf",
        "folder//document.pdf",
        "./document.pdf",
        "folder/../document.pdf",
        "folder/./document.pdf",
        "folder/",
    ],
)
def test_canonical_relpath_rejects_unsafe_paths(value: str) -> None:
    with pytest.raises(ValueError):
        canonical_relpath(value)


def test_document_identity_is_portable_between_raw_roots() -> None:
    source_relpath = canonical_relpath("manual/subfolder/document.pdf")
    first_root = Path("C:/first/docs_raw")
    moved_root = Path("D:/moved/docs_raw")

    first_source = first_root / Path(source_relpath)
    moved_source = moved_root / Path(source_relpath)

    assert first_source != moved_source
    assert stable_document_id(source_relpath) == stable_document_id(
        moved_source.relative_to(moved_root).as_posix()
    )
    assert ArtifactPaths.for_source(source_relpath) == ArtifactPaths.for_source(
        moved_source.relative_to(moved_root).as_posix()
    )


@pytest.mark.parametrize(
    ("source", "stem"),
    [
        (
            "manual/1761580555950_syc_RE.RH-04SST23102025.pdf",
            "manual/1761580555950_syc_RE.RH-04SST23102025",
        ),
        (
            "manual/1761609513260_syc_RG.RH-01-SST23102025.pdf",
            "manual/1761609513260_syc_RG.RH-01-SST23102025",
        ),
        (
            "capacitaciones/1711493199040_syc_pg-rh-10-sst.program.pdf",
            "capacitaciones/1711493199040_syc_pg-rh-10-sst.program",
        ),
    ],
)
def test_artifact_paths_remove_only_the_final_source_extension(
    source: str, stem: str
) -> None:
    paths = ArtifactPaths.for_source(source)

    assert paths.normalized_base == stem
    assert paths.markdown == f"{stem}.md"
    assert paths.metadata == f"{stem}.metadata.json"
    assert paths.pages == f"{stem}.pages.json"
    assert paths.ocr == f"{stem}.ocr.json"
    assert paths.tables == f"{stem}.tables.json"
    assert paths.forms == f"{stem}.forms.json"


def test_preflight_artifact_paths_rejects_colliding_source_stems() -> None:
    with pytest.raises(ValueError, match="collision"):
        preflight_artifact_paths(["manual/document.pdf", "manual/document.md"])


def test_preflight_artifact_paths_rejects_duplicate_sources() -> None:
    with pytest.raises(ValueError, match="collision"):
        preflight_artifact_paths(["manual/document.pdf", "manual/document.pdf"])


def test_stable_document_id_preserves_existing_sha1_algorithm() -> None:
    assert stable_document_id("manual/document.pdf") == "doc_2b3c08e8f7c22fc6"
