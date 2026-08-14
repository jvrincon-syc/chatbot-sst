"""Etapa normalize del CLI ``run_project_ingestion.py``: resolver de plataforma.

El resolver mapea cada ``InventoryRecord`` del escaneo raw a su
``PlatformMetadataContext`` usando las revisiones ya registradas en la etapa raw.
Es la pieza pura que ``run_pipeline`` invoca por documento; aquí se prueba sin
tocar Postgres ni el motor de normalización.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]


def _load(module_name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(module_name, _ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _Id:
    def __init__(self, value: str) -> None:
        self.value = value


class _Revision:
    """Stub de ``SourceDocumentRevision`` con solo los campos que lee el resolver."""

    def __init__(self, *, logical: str, revision: str) -> None:
        self.logical_document_id = _Id(logical)
        self.source_document_revision_id = _Id(revision)


class _Record:
    """Stub de ``InventoryRecord``: el resolver solo lee ``source_relpath``."""

    def __init__(self, source_relpath: str) -> None:
        self.source_relpath = source_relpath


_FP = "a" * 64
_RECIPE = "b" * 64


def test_resolver_mapea_revision_registrada_a_contexto_de_plataforma() -> None:
    module = _load("run_project_ingestion_cli", "scripts/rag_platform/run_project_ingestion.py")

    resolver = module._build_platform_context_resolver(
        project_id="proj_sst-general",
        revisions_by_relpath={"general/manual.md": _Revision(logical="sdoc_x", revision="srev_x")},
        processing_profile_id="pp_local",
        processing_profile_fingerprint=_FP,
        rag_variant_id="ragv_bge",
        semantic_recipe_fingerprint=_RECIPE,
    )

    context = resolver(_Record("general/manual.md"))

    assert context is not None
    assert context.project_id == "proj_sst-general"
    assert context.source_document_id == "sdoc_x"
    assert context.source_document_revision_id == "srev_x"
    assert context.processing_profile_id == "pp_local"
    assert context.processing_profile_fingerprint == _FP
    assert context.normalized_document_id.startswith("ndoc_")
    assert context.rag_variant_id == "ragv_bge"
    assert context.semantic_recipe_fingerprint == _RECIPE


def test_resolver_devuelve_none_para_documento_sin_revision() -> None:
    module = _load("run_project_ingestion_cli", "scripts/rag_platform/run_project_ingestion.py")

    resolver = module._build_platform_context_resolver(
        project_id="proj_sst-general",
        revisions_by_relpath={"general/manual.md": _Revision(logical="sdoc_x", revision="srev_x")},
        processing_profile_id="pp_local",
        processing_profile_fingerprint=_FP,
        rag_variant_id=None,
        semantic_recipe_fingerprint=None,
    )

    # Documento no registrado en la etapa raw: el pipeline lo normaliza sin
    # identidad de plataforma (legacy inerte) en vez de abortar.
    assert resolver(_Record("otro/doc.md")) is None
