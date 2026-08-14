"""Regresión mínima de normalización: local y LlamaCloud parse sobre 3 tipos.

Verifica lo que el legacy ya hacía: normalizar (a) un ``.md``, (b) un PDF de
**texto** (capa digital, sin OCR) y (c) un PDF **escaneado** (requiere OCR),
por los dos proveedores de parseo:

- ``test_normaliza_local_los_tres_tipos`` — motor on-prem (pdfium + tesseract OCR).
- ``test_normaliza_llamacloud_los_tres_tipos`` — microservicio LlamaCloud parse.

Ambos son de integración y dependen del corpus real bajo
``data/projects/sst-general/raw`` (marcador ``corpus``). El de LlamaCloud, además,
se **salta** si el módulo ``llama_cloud`` no está instalado o falta
``LLAMA_CLOUD_API_KEY`` (nunca inventa un run cloud).

Uso:
    npm run python -- -m pytest app/back/tests/ingestion/test_normalize_local_and_llamacloud.py -v -m corpus
    # solo el cloud (requiere módulo + API key + autorización de datos):
    npm run python -- -m pytest app/back/tests/ingestion/test_normalize_local_and_llamacloud.py::test_normaliza_llamacloud_los_tres_tipos -v
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

from ingestion.config.env import load_secrets_env
from ingestion.pipeline import run_pipeline

_REPO_ROOT = Path(__file__).resolve().parents[4]
_RAW_ROOT = _REPO_ROOT / "data" / "projects" / "sst-general" / "raw"

#: (source_relpath, tipo esperado) de los tres archivos de referencia.
_MD = "convivencia_laboral/manual/introduccion.md"
_PDF_TEXTO = "convivencia_laboral/manual/1761580555950_syc_RE.RH-04SST23102025.pdf"
_PDF_ESCANEADO = "convivencia_laboral/manual/1781045303349_syc_politicadedesconexin.pdf"
_THREE = (_MD, _PDF_TEXTO, _PDF_ESCANEADO)


def _normalized_md_path(root: Path, source_relpath: str) -> Path:
    """Ruta del markdown normalizado que corresponde a un ``source_relpath``."""

    return root / Path(source_relpath).with_suffix(".md")


def _load_metadata(root: Path, source_relpath: str) -> dict[str, object]:
    meta = root / Path(source_relpath).with_suffix(".metadata.json")
    return json.loads(meta.read_text(encoding="utf-8"))


def _run(docs_normalized: Path, *, cloud_enabled: bool) -> dict[str, int]:
    """Corre la normalización de los tres archivos con el proveedor pedido.

    ``load_secrets_env`` (setdefault) trae credenciales/rutas OCR; el flag de cloud
    se fuerza *después* para ganarle a lo heredado del entorno. ``promote=False``:
    solo queremos el artefacto normalizado, no el gate de elegibilidad.
    """

    load_secrets_env(_REPO_ROOT / "secrets.env")
    os.environ["LLAMA_CLOUD_ENABLED"] = "true" if cloud_enabled else "false"
    if cloud_enabled:
        # Este test valida el **parse** cloud (capacidad obligatoria del lane).
        # ``classify`` y ``extract`` son stops opcionales y features de plan pago de
        # LlamaCloud (devuelven 403 en free-tier); se apagan para no acoplar la prueba
        # del parse a una suscripción. El orquestador salta los stops deshabilitados.
        os.environ["LLAMA_CLASSIFY_ENABLED"] = "false"
        os.environ["LLAMA_EXTRACT_ENABLED"] = "false"
    return run_pipeline(
        docs_raw=_RAW_ROOT,
        docs_normalized=docs_normalized,
        only_sources=list(_THREE),
        force=True,
        promote=False,
        corpus_version="test-normalize",
        pipeline_version="2.0.0",
        request_id="test_normalize",
    )


def _assert_three_normalized(root: Path) -> None:
    """Cada uno de los tres produce markdown normalizado no vacío y clasificado."""

    for source_relpath in _THREE:
        md = _normalized_md_path(root, source_relpath)
        assert md.exists(), f"falta normalizado de {source_relpath}"
        assert md.read_text(encoding="utf-8").strip(), f"normalizado vacío: {source_relpath}"
        metadata = _load_metadata(root, source_relpath)
        assert metadata["processing_status"] in {"processed", "needs_review"}
        assert int(metadata["page_count"]) >= 1


@pytest.mark.corpus
def test_normaliza_local_los_tres_tipos(tmp_path: Path) -> None:
    if not _RAW_ROOT.exists():
        pytest.skip(f"corpus ausente: {_RAW_ROOT}")

    summary = _run(tmp_path, cloud_enabled=False)

    _assert_three_normalized(tmp_path)
    # El path local distingue texto (capa digital) de escaneado (OCR real).
    assert _load_metadata(tmp_path, _PDF_ESCANEADO)["extraction_method"] == "ocr"
    assert _load_metadata(tmp_path, _PDF_TEXTO)["extraction_method"] != "ocr"
    assert _load_metadata(tmp_path, _MD)["extraction_method"] == "markdown"
    assert summary["failed"] == 0


@pytest.mark.corpus
def test_normaliza_llamacloud_los_tres_tipos(tmp_path: Path) -> None:
    if not _RAW_ROOT.exists():
        pytest.skip(f"corpus ausente: {_RAW_ROOT}")
    if importlib.util.find_spec("llama_cloud") is None:
        pytest.skip("modulo llama_cloud no instalado")
    if not (os.getenv("LLAMA_CLOUD_API_KEY") or "").strip():
        # secrets.env puede traerla; se comprueba tras cargarla.
        load_secrets_env(_REPO_ROOT / "secrets.env")
        if not (os.getenv("LLAMA_CLOUD_API_KEY") or "").strip():
            pytest.skip("falta LLAMA_CLOUD_API_KEY")

    summary = _run(tmp_path, cloud_enabled=True)

    # Con LlamaCloud los tres deben normalizarse igual (los PDFs vía el microservicio).
    _assert_three_normalized(tmp_path)
    assert summary["failed"] == 0
