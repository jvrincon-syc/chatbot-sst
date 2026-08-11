from __future__ import annotations

from pathlib import Path

import pytest

from pydantic import ValidationError

from ingestion.paths import (
    ArtifactPaths,
    canonical_relpath,
    platform_document_id,
    platform_revision_id,
    preflight_artifact_paths,
    stable_document_id,
)
from ingestion.schemas.artifacts import MetadataArtifact, PlatformDocumentIdentity


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


def test_platform_document_id_is_project_scoped() -> None:
    # Misma ruta relativa en dos proyectos => identidades lógicas distintas.
    a = platform_document_id("sst-general", "manual/document.pdf")
    b = platform_document_id("calidad-interna", "manual/document.pdf")
    assert a.startswith("sdoc_")
    assert a != b
    # Determinista: misma entrada => misma identidad.
    assert a == platform_document_id("sst-general", "manual/document.pdf")


def test_platform_revision_id_changes_with_raw_hash() -> None:
    first = platform_revision_id("sst-general", "manual/document.pdf", "hash-v1")
    second = platform_revision_id("sst-general", "manual/document.pdf", "hash-v2")
    assert first.startswith("srev_")
    assert first != second  # bytes distintos => revisión distinta
    # El legacy sigue intacto: la identidad de plataforma no lo replica.
    assert first != stable_document_id("manual/document.pdf")


def test_platform_revision_id_requires_raw_hash() -> None:
    with pytest.raises(ValueError):
        platform_revision_id("sst-general", "manual/document.pdf", "")


# --- Fase 2: extensión aditiva del contrato Schema 2.0 (ADR-006) -------------


def test_metadata_platform_identity_is_optional_for_legacy() -> None:
    # El adaptador legacy no emite platform_identity: el default es None y los
    # artefactos SST validan sin cambios.
    field = MetadataArtifact.model_fields["platform_identity"]
    assert field.default is None
    assert not field.is_required()


def test_platform_document_identity_accepts_typed_locators() -> None:
    identity = PlatformDocumentIdentity(
        project_id="proj_sst-general",
        source_document_id=platform_document_id("sst-general", "manual/x.pdf"),
        source_document_revision_id=platform_revision_id(
            "sst-general", "manual/x.pdf", "hash-v1"
        ),
        processing_profile_id="pp_local-pdf-ocr-v1",
        processing_profile_fingerprint="a" * 64,
    )
    assert identity.normalized_document_id is None  # generador llega en fase posterior
    assert identity.schema_version == "2.0"


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("project_id", "sst-general"),  # sin prefijo proj_
        ("source_document_revision_id", "proj_x"),  # prefijo equivocado
        ("processing_profile_fingerprint", "not-hex"),  # fingerprint inválido
    ],
)
def test_platform_document_identity_rejects_malformed_ids(field: str, bad_value: str) -> None:
    valid = dict(
        project_id="proj_sst-general",
        source_document_id="sdoc_abc",
        source_document_revision_id="srev_abc",
        processing_profile_id="pp_local",
        processing_profile_fingerprint="a" * 64,
    )
    valid[field] = bad_value
    with pytest.raises(ValidationError):
        PlatformDocumentIdentity(**valid)
