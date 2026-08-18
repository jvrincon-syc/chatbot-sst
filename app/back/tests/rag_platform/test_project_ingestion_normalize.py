"""Preflight fail-closed de la etapa normalize del CLI ``run_project_ingestion.py``.

``resolve_platform_contexts_or_raise`` resuelve la identidad de plataforma de
*todos* los documentos seleccionados antes de leer/escribir/promover ninguno. Un
documento seleccionado sin revisión registrada aborta el normalize completo con
``platform_identity_incomplete`` (Task 1), en vez del comportamiento legacy
fail-open que normalizaba sin identidad. Pieza pura: sin Postgres ni motor de
normalización.
"""

from __future__ import annotations

import pytest

from ingestion.application.platform_metadata import (
    PlatformContextResolutionError,
    resolve_platform_contexts_or_raise,
)


class _Id:
    def __init__(self, value: str) -> None:
        self.value = value


class _Revision:
    """Stub de ``SourceDocumentRevision`` con solo los campos que lee el preflight."""

    def __init__(self, *, logical: str, revision: str) -> None:
        self.logical_document_id = _Id(logical)
        self.source_document_revision_id = _Id(revision)


class _Record:
    """Stub de ``InventoryRecord``: el preflight solo lee ``source_relpath``."""

    def __init__(self, source_relpath: str) -> None:
        self.source_relpath = source_relpath


_FP = "a" * 64
_RECIPE = "b" * 64


def test_preflight_falla_si_un_record_seleccionado_no_tiene_revision() -> None:
    records = [_Record("a/manual.pdf"), _Record("b/manual.pdf")]
    revisions = {"a/manual.pdf": _Revision(logical="sdoc_a", revision="srev_a")}

    with pytest.raises(PlatformContextResolutionError, match="b/manual.pdf"):
        resolve_platform_contexts_or_raise(
            records=records,
            revisions_by_relpath=revisions,
            project_id="proj_demo",
            processing_profile_id="pp_local",
            processing_profile_fingerprint=_FP,
            rag_variant_id="ragv_demo",
            semantic_recipe_fingerprint=_RECIPE,
        )


def test_preflight_mapea_todas_las_revisiones_registradas() -> None:
    records = [_Record("general/manual.md")]
    revisions = {"general/manual.md": _Revision(logical="sdoc_x", revision="srev_x")}

    resolved = resolve_platform_contexts_or_raise(
        records=records,
        revisions_by_relpath=revisions,
        project_id="proj_sst-general",
        processing_profile_id="pp_local",
        processing_profile_fingerprint=_FP,
        rag_variant_id="ragv_bge",
        semantic_recipe_fingerprint=_RECIPE,
    )

    context = resolved["general/manual.md"]
    assert context.project_id == "proj_sst-general"
    assert context.source_document_id == "sdoc_x"
    assert context.source_document_revision_id == "srev_x"
    assert context.processing_profile_id == "pp_local"
    assert context.processing_profile_fingerprint == _FP
    assert context.normalized_document_id.startswith("ndoc_")
    assert context.rag_variant_id == "ragv_bge"
    assert context.semantic_recipe_fingerprint == _RECIPE
