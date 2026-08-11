from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

import scripts.rag_platform.reset_derived_rag_artifacts as reset_script
from scripts.rag_platform.reset_derived_rag_artifacts import (
    DELETE_TABLES_IN_ORDER,
    _assert_within_repo,
    _delete_filesystem,
    _delete_tables,
    apply_reset,
    blockers_from_counts,
    derived_paths,
    dry_run_report,
)


def test_blockers_from_counts_no_bloquea_sin_actividad() -> None:
    blockers = blockers_from_counts(
        active_retrieval_profiles=0,
        active_vector_rows_by_table={
            "idx_vec_local_bge_m3_v1": 0,
            "idx_vec_llama_bge_m3_v1": 0,
        },
    )

    assert blockers["has_blockers"] is False
    assert blockers["vector_tables_with_rows"] == []


def test_blockers_from_counts_bloquea_por_retrieval_activo_o_filas_activas() -> None:
    blockers = blockers_from_counts(
        active_retrieval_profiles=1,
        active_vector_rows_by_table={
            "idx_vec_local_bge_m3_v1": 3,
            "idx_vec_llama_bge_m3_v1": 0,
        },
    )

    assert blockers["has_blockers"] is True
    assert blockers["active_retrieval_profiles"] == 1
    assert blockers["vector_tables_with_rows"] == ["idx_vec_local_bge_m3_v1"]


def test_dry_run_report_expone_plan_e_inventario(tmp_path: Path) -> None:
    project_root = tmp_path / "data" / "projects" / "acme"
    (project_root / "raw").mkdir(parents=True)
    (project_root / "normalized").mkdir()

    inventory = {
        "idx_vec_tables": ["idx_vec_local_bge_m3_v1"],
        "tables": {"retrieval_profiles": {"count": 0}},
    }
    blockers = blockers_from_counts(
        active_retrieval_profiles=0,
        active_vector_rows_by_table={"idx_vec_local_bge_m3_v1": 0},
    )

    report = dry_run_report(
        repo_root=tmp_path,
        inventory_before=inventory,
        blockers=blockers,
    )

    assert report["mode"] == "dry_run"
    assert report["status"] == "planned"
    assert report["delete_tables_in_order"] == list(DELETE_TABLES_IN_ORDER)
    assert report["inventory_before"] == inventory
    assert report["inventory-before"] == inventory
    assert isinstance(report["confirmation_token"], str)
    assert len(report["confirmation_token"]) == 16
    paths = {item["path"] for item in report["filesystem_targets"]}
    assert str(tmp_path / "data" / "chunks") in paths
    assert str(project_root / "chunks") in paths
    assert str(project_root / "raw") not in paths


def test_apply_reset_falla_cerrado_si_hay_blockers(tmp_path: Path) -> None:
    inventory = {
        "idx_vec_tables": ["idx_vec_local_bge_m3_v1"],
        "tables": {"retrieval_profiles": {"count": 2}},
    }
    blockers = blockers_from_counts(
        active_retrieval_profiles=2,
        active_vector_rows_by_table={"idx_vec_local_bge_m3_v1": 1},
    )

    result = apply_reset(
        repo_root=tmp_path,
        dsn="postgresql://ignored",
        inventory_before=inventory,
        blockers=blockers,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "active_legacy_state_present"
    assert "inventory_after" not in result


def test_delete_tables_borra_primero_vectores_y_luego_tablas_derivadas() -> None:
    inventory = {
        "idx_vec_tables": ["idx_vec_local_bge_m3_v1", "idx_vec_llama_bge_m3_v1"],
    }
    cursor = RecordingCursor()

    deleted = _delete_tables(cursor, inventory_before=inventory)

    assert cursor.statements[:2] == [
        "DELETE FROM idx_vec_local_bge_m3_v1",
        "DELETE FROM idx_vec_llama_bge_m3_v1",
    ]
    assert cursor.statements[2:] == [f"DELETE FROM {name}" for name in DELETE_TABLES_IN_ORDER]
    assert deleted["idx_vec_local_bge_m3_v1"] == 1
    assert deleted["chunk_bundles"] == 10


def test_derived_paths_y_delete_filesystem_preservan_raw_y_normalized(tmp_path: Path) -> None:
    legacy_chunks = tmp_path / "data" / "chunks"
    legacy_embeddings = tmp_path / "data" / "embeddings"
    project_root = tmp_path / "data" / "projects" / "acme"
    preserved = [project_root / "raw", project_root / "normalized"]
    derived = [
        legacy_chunks,
        legacy_embeddings,
        project_root / "chunks",
        project_root / "embeddings",
        project_root / "manifests",
    ]

    for path in preserved + derived:
        path.mkdir(parents=True, exist_ok=True)
        (path / "marker.txt").write_text("x", encoding="utf-8")

    paths = derived_paths(tmp_path)

    assert project_root / "raw" not in paths
    assert project_root / "normalized" not in paths
    assert project_root / "chunks" in paths

    _delete_filesystem(paths, repo_root=tmp_path)

    for path in preserved:
        assert path.exists()
        assert (path / "marker.txt").exists()
    for path in derived:
        assert not path.exists()


def test_apply_reset_exitoso_devuelve_inventory_after_y_preserva_fuentes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "data" / "projects" / "acme"
    preserved = [project_root / "raw", project_root / "normalized"]
    derived = [
        tmp_path / "data" / "chunks",
        tmp_path / "data" / "embeddings",
        project_root / "chunks",
        project_root / "embeddings",
        project_root / "manifests",
    ]
    for path in preserved + derived:
        path.mkdir(parents=True, exist_ok=True)
        (path / "marker.txt").write_text("x", encoding="utf-8")

    inventory_before = {
        "idx_vec_tables": ["idx_vec_local_bge_m3_v1"],
        "tables": {"retrieval_profiles": {"count": 0}},
    }
    blockers = blockers_from_counts(
        active_retrieval_profiles=0,
        active_vector_rows_by_table={"idx_vec_local_bge_m3_v1": 0},
    )

    class FakeCursor:
        def __init__(self) -> None:
            self.statements: list[str] = []
            self.rowcount = 1

        def execute(self, statement: str) -> None:
            self.statements.append(statement)

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_instance = FakeCursor()
            self.closed = False

        def cursor(self) -> FakeCursor:
            return self.cursor_instance

        def close(self) -> None:
            self.closed = True

        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    fake_connection = FakeConnection()
    monkeypatch.setitem(
        sys.modules,
        "psycopg2",
        SimpleNamespace(connect=lambda **_: fake_connection),
    )
    monkeypatch.setitem(
        sys.modules,
        "psycopg2.extensions",
        SimpleNamespace(parse_dsn=lambda dsn: {"dsn": dsn}),
    )
    monkeypatch.setattr(
        reset_script,
        "collect_inventory",
        lambda dsn: {"tables": {"chunk_bundles": {"count": 0}}, "idx_vec_tables": []},
    )

    result = apply_reset(
        repo_root=tmp_path,
        dsn="postgresql://reset",
        inventory_before=inventory_before,
        blockers=blockers,
    )

    assert result["status"] == "applied"
    assert "inventory_after" in result
    assert "inventory-after-reset" in result
    assert fake_connection.closed is True
    assert fake_connection.cursor_instance.statements[:2] == [
        "DELETE FROM idx_vec_local_bge_m3_v1",
        "DELETE FROM indexing_run_documents",
    ]
    for path in preserved:
        assert path.exists()
    for path in derived:
        assert not path.exists()


def test_assert_within_repo_rechaza_ruta_fuera_del_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere"

    with pytest.raises(ValueError):
        _assert_within_repo(outside, repo_root=tmp_path)


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.rowcount = 0
        self._count = 0

    def execute(self, statement: str) -> None:
        self.statements.append(statement)
        self._count += 1
        self.rowcount = self._count
