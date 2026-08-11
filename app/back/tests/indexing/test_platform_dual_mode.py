from __future__ import annotations

from pathlib import Path

from indexing.application.bundle_first.activation import ActivationRequest
from rag_platform.domain.identity import physical_node_id

from pipeline_fixtures import build_pipeline_stack


def test_legacy_activation_still_activates_legacy_bundle(tmp_path: Path) -> None:
    stack = build_pipeline_stack(tmp_path)

    embedding_bundle_id = stack.run_embedding()
    run_id = stack.run_indexing(embedding_bundle_id)
    activation = stack.activate_bundle.execute(
        ActivationRequest(
            run_id=run_id,
            consumer_scope_type="chatbot",
            consumer_scope_id="sst-default",
        )
    )

    child_nodes = [node for node in stack.nodes.nodes.values() if node.node_role == "child"]
    assert child_nodes
    assert all(node.project_id is None for node in child_nodes)
    assert all(node.source_chunk_id is None for node in child_nodes)
    assert {node.node_id for node in child_nodes} == {
        row.record.node_id for row in stack.vectors.rows.values()
    }
    assert all(row.record.project_id is None for row in stack.vectors.rows.values())
    assert {row.record.embedding_bundle_id for row in stack.vectors.active_rows()} == {
        embedding_bundle_id
    }
    assert activation.activated_rows == len(child_nodes)
    assert stack.indexing_runs.get(run_id).activation_status == "active"


def test_platform_indexing_does_not_activate_vectors(tmp_path: Path) -> None:
    stack = build_pipeline_stack(tmp_path)
    project_id = "proj_alpha"
    project_bundle = stack.chunk_bundle.model_copy(update={"project_id": project_id})
    stack.chunk_bundle = project_bundle
    stack.chunk_bundles.ensure_registered(project_bundle)

    embedding_bundle_id = stack.run_embedding()
    run_id = stack.run_indexing(embedding_bundle_id)

    child_nodes = [node for node in stack.nodes.nodes.values() if node.node_role == "child"]
    assert child_nodes
    expected_child_ids = {
        physical_node_id(
            project_id=project_id,
            source_chunk_bundle_id=project_bundle.chunk_bundle_id,
            source_chunk_id=str(node.source_chunk_id),
        )
        for node in child_nodes
    }
    actual_vector_ids = {row.record.node_id for row in stack.vectors.rows.values()}

    assert {node.node_id for node in child_nodes} == expected_child_ids
    assert actual_vector_ids == expected_child_ids
    assert {row.record.project_id for row in stack.vectors.rows.values()} == {project_id}
    assert all(row.record.metadata["parent_node_id"] in stack.nodes.nodes for row in stack.vectors.rows.values())
    assert all(not row.is_active for row in stack.vectors.rows.values())
    assert stack.indexing_runs.get(run_id).activation_status == "pending"


def test_platform_materialization_not_visible_to_legacy_retrieval(tmp_path: Path) -> None:
    stack = build_pipeline_stack(tmp_path)

    legacy_bundle_id = stack.run_embedding()
    legacy_run_id = stack.run_indexing(legacy_bundle_id)
    activation = stack.activate_bundle.execute(
        ActivationRequest(
            run_id=legacy_run_id,
            consumer_scope_type="chatbot",
            consumer_scope_id="sst-default",
        )
    )
    legacy_profile = stack.retrieval_profiles.get(activation.retrieval_profile_id)
    legacy_results = stack.search.search(
        retrieval_profile=legacy_profile,
        query="safety rules",
    )

    project_id = "proj_alpha"
    project_bundle = stack.chunk_bundle.model_copy(update={"project_id": project_id})
    stack.chunk_bundle = project_bundle
    stack.chunk_bundles.ensure_registered(project_bundle)
    platform_bundle_id = stack.run_embedding(idempotency_key="embed-platform")
    stack.run_indexing(platform_bundle_id, idempotency_key="index-platform")

    results_after_platform_indexing = stack.search.search(
        retrieval_profile=legacy_profile,
        query="safety rules",
    )
    platform_node_ids = {
        node.node_id
        for node in stack.nodes.nodes.values()
        if node.project_id == project_id
    }

    assert legacy_results
    assert all(
        not row.is_active for row in stack.vectors.rows.values() if row.record.project_id == project_id
    )
    assert [item.node_id for item in results_after_platform_indexing] == [
        item.node_id for item in legacy_results
    ]
    assert platform_node_ids.isdisjoint(
        {item.node_id for item in results_after_platform_indexing}
    )
