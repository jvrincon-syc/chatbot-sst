"""Task 5: el pipeline escribe identidad y provenance de plataforma (aditivo).

Cuando ``run_pipeline`` recibe un ``platform_context_resolver`` escribe en el
metadata sidecar dos bloques nuevos: ``platform_identity`` (proyecto, documento,
revisión y perfil) y ``platform_provenance`` (variante y receta semántica). Sin
resolver, o con un resolver que devuelve ``None``, el sidecar legacy queda
inerte: los dos bloques quedan en ``null`` y el resto no cambia.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.application.platform_metadata import (
    PlatformMetadataContext,
    apply_platform_metadata,
)
from ingestion.pipeline import run_pipeline
from ingestion.schemas.artifacts import (
    Classification,
    DocumentControl,
    MetadataArtifact,
)
from ingestion.schemas.common import ConfidenceMetric, DocumentField, Observation

_PP_FP = "a" * 64
_RECIPE_FP = "b" * 64


@pytest.fixture(autouse=True)
def _local_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_CLOUD_ENABLED", "false")
    monkeypatch.delenv("LLAMA_CLOUD_API_KEY", raising=False)


def _context() -> PlatformMetadataContext:
    return PlatformMetadataContext(
        project_id="proj_sst-general",
        source_document_id="sdoc_manual",
        source_document_revision_id="srev_manual",
        processing_profile_id="pp_local-pdf",
        processing_profile_fingerprint=_PP_FP,
        normalized_document_id="ndoc_manual",
        rag_variant_id="ragv_local-bge",
        semantic_recipe_fingerprint=_RECIPE_FP,
    )


def _seed_corpus(root: Path) -> None:
    (root / "general").mkdir(parents=True)
    (root / "general" / "manual.md").write_text(
        "# Manual\n\nContenido", encoding="utf-8"
    )


def test_escribe_platform_identity_y_provenance_cuando_resolver_presente(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "docs_raw"
    normalized = tmp_path / "docs_normalized"
    _seed_corpus(raw)

    summary = run_pipeline(
        docs_raw=raw,
        docs_normalized=normalized,
        run_id="platform-test",
        corpus_version="test",
        pipeline_version="2.0.0",
        platform_context_resolver=lambda record: _context(),
    )

    assert summary["processed"] == 1
    payload = json.loads(
        (normalized / "general" / "manual.metadata.json").read_text(encoding="utf-8")
    )
    assert payload["platform_identity"]["project_id"] == "proj_sst-general"
    assert payload["platform_identity"]["source_document_revision_id"] == "srev_manual"
    assert payload["platform_identity"]["normalized_document_id"] == "ndoc_manual"
    assert payload["platform_provenance"]["rag_variant_id"] == "ragv_local-bge"
    assert payload["platform_provenance"]["semantic_recipe_fingerprint"] == _RECIPE_FP


def test_sidecar_legacy_deja_bloques_nulos_cuando_resolver_none(tmp_path: Path) -> None:
    raw = tmp_path / "docs_raw"
    normalized = tmp_path / "docs_normalized"
    _seed_corpus(raw)

    run_pipeline(
        docs_raw=raw,
        docs_normalized=normalized,
        run_id="legacy-test",
        corpus_version="test",
        pipeline_version="2.0.0",
    )

    payload = json.loads(
        (normalized / "general" / "manual.metadata.json").read_text(encoding="utf-8")
    )
    assert payload["platform_identity"] is None
    assert payload["platform_provenance"] is None


def test_resolver_que_devuelve_none_es_byte_identico_al_legacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Congela el reloj para que dos corridas independientes sean comparables byte
    # a byte; así el único delta posible sería el path de plataforma.
    monkeypatch.setattr(
        "ingestion.pipeline._now", lambda: "2026-08-12T00:00:00+00:00"
    )
    raw = tmp_path / "docs_raw"
    normalized = tmp_path / "norm"
    _seed_corpus(raw)
    sidecar = normalized / "general" / "manual.metadata.json"

    def _run(resolver) -> bytes:
        # Sobrescribe el mismo destino: el único delta posible es el path de
        # plataforma, no rutas absolutas ni el reloj (congelado).
        run_pipeline(
            docs_raw=raw,
            docs_normalized=normalized,
            run_id="byte-identity",
            corpus_version="test",
            pipeline_version="2.0.0",
            force=True,
            platform_context_resolver=resolver,
        )
        return sidecar.read_bytes()

    legacy = _run(None)
    inert = _run(lambda record: None)
    assert legacy == inert


def _metadata() -> MetadataArtifact:
    unavailable = ConfidenceMetric(kind="unavailable", value=None)
    not_evaluated = Observation(status="not_evaluated", value=None)
    empty_field = DocumentField(value=None, status="not_evaluated")
    return MetadataArtifact(
        schema_version="2.0",
        document_id="doc_1",
        document_name="manual.md",
        source_relpath="general/manual.md",
        normalized_relpath="general/manual.md",
        document_control=DocumentControl(
            title=empty_field,
            code=empty_field,
            version=empty_field,
            publication_date=empty_field,
            effective_date=empty_field,
        ),
        classification=Classification(
            document_type="otro",
            document_type_confidence=unavailable,
            topic="general",
            topic_confidence=unavailable,
        ),
        page_count=1,
        extraction_method="markdown",
        ocr_confidence=unavailable,
        handwriting=not_evaluated,
        tables=not_evaluated,
        forms=not_evaluated,
        source_hash="d" * 64,
        corpus_version="test",
        pipeline_version="2.0.0",
        processing_status="processed",
    )


def test_apply_platform_metadata_no_muta_el_original() -> None:
    original = _metadata()

    enriched = apply_platform_metadata(original, _context())

    # El original no se toca (función pura): sigue sin identidad de plataforma.
    assert original.platform_identity is None
    assert original.platform_provenance is None
    assert enriched.platform_identity is not None
    assert enriched.platform_identity.project_id == "proj_sst-general"
    # La identidad no arrastra la provenance: es un bloque separado.
    assert enriched.platform_identity.rag_variant_id is None
    assert enriched.platform_provenance is not None
    assert enriched.platform_provenance.rag_variant_id == "ragv_local-bge"
    assert enriched.platform_provenance.semantic_recipe_fingerprint == _RECIPE_FP


def test_apply_platform_metadata_deja_provenance_vacia_sin_variant() -> None:
    context = PlatformMetadataContext(
        project_id="proj_sst-general",
        source_document_id="sdoc_manual",
        source_document_revision_id="srev_manual",
        processing_profile_id="pp_local-pdf",
        processing_profile_fingerprint=_PP_FP,
    )

    enriched = apply_platform_metadata(_metadata(), context)

    assert enriched.platform_identity is not None
    assert enriched.platform_provenance is not None
    assert enriched.platform_provenance.rag_variant_id is None
    assert enriched.platform_provenance.semantic_recipe_fingerprint is None
