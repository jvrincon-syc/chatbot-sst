from __future__ import annotations

from pathlib import Path

from indexing.application.bundle_first.index_bundle import CreateIndexingRunRequest

from pipeline_fixtures import build_pipeline_stack


def test_create_indexing_run_persiste_contexto_de_release(tmp_path: Path) -> None:
    stack = build_pipeline_stack(tmp_path)
    embedding_bundle_id = stack.run_embedding()

    run = stack.create_indexing_run.execute(
        request=CreateIndexingRunRequest(
            embedding_bundle_id=embedding_bundle_id,
            project_id="proj_alpha",
            rag_variant_id="ragv_alpha",
            rag_release_id="ragr_alpha",
        ),
        idempotency_key="index-platform-context",
    )

    assert run.project_id == "proj_alpha"
    assert run.rag_variant_id == "ragv_alpha"
    assert run.rag_release_id == "ragr_alpha"
