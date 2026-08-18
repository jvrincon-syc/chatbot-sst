from __future__ import annotations

"""Pure-platform bundle-first indexing remains the supported lane.

Task 5 quarantines platform-owned normalized documents from the legacy
`scripts/indexing/run_indexing.py --store postgres` lane. These tests keep the
bundle-first project-owned path explicit and independent from that legacy CLI.
"""

from pathlib import Path

from indexing.application.bundle_first.activation import ActivationRequest
from rag_platform.domain.identity import physical_node_id

from pipeline_fixtures import build_pipeline_stack, write_chunk_bundle


def test_activation_activates_platform_bundle(tmp_path: Path) -> None:
    # ADR-008 (pure-platform): todo bundle es de plataforma (project_id obligatorio).
    # La activación explícita sigue operando sobre el run indexado.
    stack = build_pipeline_stack(tmp_path)
    project_id = "proj_alpha"
    stack.chunk_bundle = stack.chunk_bundle.model_copy(update={"project_id": project_id})
    stack.chunk_bundles.ensure_registered(stack.chunk_bundle)

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
    # Nodos y vectores son físicos namespaced, con dueño de proyecto.
    assert all(node.project_id == project_id for node in child_nodes)
    assert all(node.source_chunk_id is not None for node in child_nodes)
    assert {node.node_id for node in child_nodes} == {
        row.record.node_id for row in stack.vectors.rows.values()
    }
    assert all(row.record.project_id == project_id for row in stack.vectors.rows.values())
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


def test_other_project_indexing_not_visible_to_active_retrieval(tmp_path: Path) -> None:
    # ADR-008: aislamiento cross-proyecto. Un bundle de otro proyecto, indexado pero
    # no activado, es invisible a la retrieval activa del proyecto A (SST dormido +
    # propiedad física por proyecto). Sustituye al viejo test legacy-vs-plataforma.
    stack = build_pipeline_stack(tmp_path)

    project_a = "proj_alpha"
    stack.chunk_bundle = stack.chunk_bundle.model_copy(update={"project_id": project_a})
    stack.chunk_bundles.ensure_registered(stack.chunk_bundle)
    bundle_a = stack.run_embedding()
    run_a = stack.run_indexing(bundle_a)
    activation = stack.activate_bundle.execute(
        ActivationRequest(
            run_id=run_a,
            consumer_scope_type="chatbot",
            consumer_scope_id="sst-default",
        )
    )
    profile_a = stack.retrieval_profiles.get(activation.retrieval_profile_id)
    results_a = stack.search.search(retrieval_profile=profile_a, query="safety rules")

    # Segundo proyecto: chunk bundle distinto (otro documento), indexado sin activar.
    bundle_b_ref = write_chunk_bundle(
        tmp_path / "chunks",
        document_id="doc-beta",
        base_relpath="unit/example_beta",
        source_relpath="unit/example_beta.md",
        bundle_seed="bundle-beta",
        parent_seed="parent-beta",
        child_seed_prefix="child-beta",
    ).model_copy(update={"project_id": "proj_beta"})
    stack.chunk_bundles.ensure_registered(bundle_b_ref)
    bundle_b = stack.run_embedding(
        chunk_bundle_id=bundle_b_ref.chunk_bundle_id, idempotency_key="embed-beta"
    )
    stack.run_indexing(bundle_b, idempotency_key="index-beta")

    results_after = stack.search.search(retrieval_profile=profile_a, query="safety rules")
    project_b_node_ids = {
        node.node_id
        for node in stack.nodes.nodes.values()
        if node.project_id == "proj_beta"
    }

    assert results_a
    # El indexado de proyecto B no activa vectores (SST dormido) ni cambia lo que A ve.
    assert all(
        not row.is_active
        for row in stack.vectors.rows.values()
        if row.record.project_id == "proj_beta"
    )
    assert [item.node_id for item in results_after] == [item.node_id for item in results_a]
    assert project_b_node_ids.isdisjoint({item.node_id for item in results_after})
