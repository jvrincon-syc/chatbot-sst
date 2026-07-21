from __future__ import annotations

import importlib
import sys
from pathlib import Path
from importlib.abc import MetaPathFinder

from ingestion.pipeline import _choose_pdf_reader


class LocalReader:
    pass


class LlamaReader:
    pass


def test_choose_pdf_reader_prefers_llama_when_enabled_and_available() -> None:
    reader = _choose_pdf_reader(
        llama_cloud_enabled=True,
        local_fallback_enabled=True,
        local_reader_factory=LocalReader,
        llama_reader_factory=LlamaReader,
    )

    assert isinstance(reader, LlamaReader)


def test_choose_pdf_reader_uses_local_fallback_when_llama_disabled() -> None:
    reader = _choose_pdf_reader(
        llama_cloud_enabled=False,
        local_fallback_enabled=True,
        local_reader_factory=LocalReader,
        llama_reader_factory=LlamaReader,
    )

    assert isinstance(reader, LocalReader)


def test_choose_pdf_reader_uses_local_fallback_when_llama_factory_unavailable() -> None:
    reader = _choose_pdf_reader(
        llama_cloud_enabled=True,
        local_fallback_enabled=True,
        local_reader_factory=LocalReader,
        llama_reader_factory=None,
    )

    assert isinstance(reader, LocalReader)


class BlockLlamaCloudImport(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "llama_cloud" or fullname.startswith("llama_cloud."):
            raise ImportError("blocked llama_cloud import")
        return None


def test_pipeline_can_import_without_optional_llama_cloud_sdk(monkeypatch) -> None:
    removed_modules = {
        name: module
        for name, module in list(sys.modules.items())
        if name == "llama_cloud"
        or name.startswith("llama_cloud.")
        or name == "ingestion.pipeline"
        or name.startswith("ingestion.infrastructure.llama_cloud.client_factory")
    }
    for name in removed_modules:
        sys.modules.pop(name, None)
    blocker = BlockLlamaCloudImport()
    sys.meta_path.insert(0, blocker)
    try:
        module = importlib.import_module("ingestion.pipeline")
    finally:
        sys.meta_path.remove(blocker)
        for name, module_obj in removed_modules.items():
            sys.modules.setdefault(name, module_obj)

    assert hasattr(module, "_choose_pdf_reader")
