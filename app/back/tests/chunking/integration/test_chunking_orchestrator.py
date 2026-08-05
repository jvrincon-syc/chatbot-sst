from __future__ import annotations

from pathlib import Path

import pytest

from chunking.application.chunking_orchestrator import ChunkingOrchestrator
from chunking.application.local_chunking_engine import LocalChunkingEngine
from chunking.domain.models import ChunkingProfile, NormalizedDocumentBundle, PageTrace
from chunking.infrastructure.filesystem_chunk_repository import (
    FilesystemChunkBundleRepository,
)
from chunking.infrastructure.filesystem_run_repository import FilesystemRunRepository


def _bundle() -> NormalizedDocumentBundle:
    markdown = (
        "<!-- page: 1 -->\n\n"
        "Primer apartado con obligaciones SST.\n\n"
        "<!-- page: 2 -->\n\n"
        "Segundo apartado con responsabilidades y evidencias."
    )
    return NormalizedDocumentBundle(
        document_id="doc_orch",
        source_hash="b" * 64,
        corpus_version="phase1",
        source_relpath="manual/doc.pdf",
        normalized_relpath="manual/doc.md",
        markdown=markdown,
        page_traces=(
            PageTrace(
                page_number=1,
                char_start=0,
                char_end=54,
                text_raw="Primer apartado con obligaciones SST.",
                text_normalized="Primer apartado con obligaciones SST.",
            ),
            PageTrace(
                page_number=2,
                char_start=56,
                char_end=len(markdown),
                text_raw="Segundo apartado con responsabilidades y evidencias.",
                text_normalized="Segundo apartado con responsabilidades y evidencias.",
            ),
        ),
    )


def _orchestrator(output_root: Path) -> ChunkingOrchestrator:
    return ChunkingOrchestrator(
        engine=LocalChunkingEngine(),
        bundle_repository=FilesystemChunkBundleRepository(output_root=output_root),
        run_repository=FilesystemRunRepository(output_root=output_root),
    )


def test_segunda_corrida_reutiliza_artefactos_cuando_fingerprint_no_cambia(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    profile = ChunkingProfile.local_structural_v1()

    first = orchestrator.process_document(document=_bundle(), profile=profile)
    second = orchestrator.process_document(document=_bundle(), profile=profile)

    assert first.run_id == second.run_id
    assert first.bundle_fingerprint == second.bundle_fingerprint
    assert second.reused is True


def test_cambio_de_overlap_invalida_reutilizacion(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    base_profile = ChunkingProfile.local_structural_v1()
    updated_profile = ChunkingProfile(
        profile_id=base_profile.profile_id,
        child_min_tokens=base_profile.child_min_tokens,
        child_target_tokens=base_profile.child_target_tokens,
        child_max_tokens=base_profile.child_max_tokens,
        overlap_ratio=0.2,
        overlap_min_tokens=base_profile.overlap_min_tokens,
        overlap_max_tokens=base_profile.overlap_max_tokens,
        zero_overlap_reasons=base_profile.zero_overlap_reasons,
    )

    first = orchestrator.process_document(document=_bundle(), profile=base_profile)
    second = orchestrator.process_document(document=_bundle(), profile=updated_profile)

    assert second.reused is False
    assert second.run_id != first.run_id
    assert second.bundle_fingerprint != first.bundle_fingerprint


def test_fallo_no_deja_bundle_parcial_promovido(tmp_path: Path) -> None:
    repository = ExplodingChunkBundleRepository(output_root=tmp_path)
    document = _bundle()
    orchestrator = ChunkingOrchestrator(
        engine=LocalChunkingEngine(),
        bundle_repository=repository,
        run_repository=FilesystemRunRepository(output_root=tmp_path),
    )

    with pytest.raises(RuntimeError, match="forced promotion failure"):
        orchestrator.process_document(
            document=document,
            profile=ChunkingProfile.local_structural_v1(),
        )

    assert not repository.parent_chunks_path(document=document).exists()
    assert not repository.child_chunks_path(document=document).exists()
    assert not repository.metadata_path(document=document).exists()


class ExplodingChunkBundleRepository(FilesystemChunkBundleRepository):
    def _promote_staged_files(
        self,
        *,
        parent_stage: Path,
        child_stage: Path,
        metadata_stage: Path,
        parent_path: Path,
        child_path: Path,
        metadata_path: Path,
    ) -> None:
        parent_path.parent.mkdir(parents=True, exist_ok=True)
        parent_stage.replace(parent_path)
        if child_stage.exists():
            child_stage.unlink()
        if metadata_stage.exists():
            metadata_stage.unlink()
        raise RuntimeError("forced promotion failure")
