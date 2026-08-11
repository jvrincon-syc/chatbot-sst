"""Hard reset de artefactos derivados de plataforma RAG (Fase 4, bloque F).

Reutiliza el inventario baseline y aplica un borrado controlado solo sobre
artefactos derivados. Nunca toca `data/docs_raw`, `data/docs_normalized`,
proyectos, perfiles ni configuración.

Uso:
    npm run python -- scripts/rag_platform/reset_derived_rag_artifacts.py
    npm run python -- scripts/rag_platform/reset_derived_rag_artifacts.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "rag_platform"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "indexing"))

from inventory_baseline import collect_inventory  # noqa: E402
from prepare_postgres_indexing import build_dsn_from_env, load_env_file  # noqa: E402


DELETE_TABLES_IN_ORDER: tuple[str, ...] = (
    "indexing_run_documents",
    "indexing_runs",
    "embedding_runs",
    "indexing_nodes",
    "readiness_checks",
    "embedding_bundle_chunks",
    "embedding_bundles",
    "chunk_bundles",
)

# Solo se resetean los artefactos derivados por proyecto. `raw` y `normalized`
# permanecen intactos aunque vivan bajo `data/projects/{project_id}/`.
PROJECT_DERIVED_SUBDIRS: tuple[str, ...] = ("chunks", "embeddings", "manifests")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--confirm-token",
        help="Token emitido por el dry-run previo; obligatorio para ejecutar --apply.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--env-file", default="secrets.env")
    return parser.parse_args()


def derived_paths(repo_root: Path) -> list[Path]:
    """Return the derived filesystem roots that Fase 4 may reset."""

    derived = [
        repo_root / "data" / "chunks",
        repo_root / "data" / "embeddings",
    ]
    projects_root = repo_root / "data" / "projects"
    if not projects_root.exists():
        return derived
    for project_root in sorted(path for path in projects_root.iterdir() if path.is_dir()):
        for subdir in PROJECT_DERIVED_SUBDIRS:
            derived.append(project_root / subdir)
    return derived


def summarize_filesystem(paths: list[Path]) -> list[dict[str, object]]:
    """Describe derived filesystem paths without mutating them."""

    summary: list[dict[str, object]] = []
    for path in paths:
        if not path.exists():
            summary.append({"path": str(path), "exists": False, "kind": "missing"})
            continue
        kind = "directory" if path.is_dir() else "file"
        summary.append({"path": str(path), "exists": True, "kind": kind})
    return summary


def build_confirmation_token(
    *,
    inventory_before: dict[str, Any],
    filesystem_targets: list[dict[str, object]],
) -> str:
    """Build a deterministic token that forces an explicit dry-run/apply handshake."""

    table_digests = {
        name: table.get("content_digest")
        for name, table in inventory_before.get("tables", {}).items()
        if isinstance(table, dict)
    }
    payload = {
        "delete_tables_in_order": list(DELETE_TABLES_IN_ORDER),
        "filesystem_targets": [
            target["path"] for target in filesystem_targets if isinstance(target, dict)
        ],
        "idx_vec_tables": inventory_before.get("idx_vec_tables", []),
        "table_digests": table_digests,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def blockers_from_counts(
    *,
    active_retrieval_profiles: int,
    active_vector_rows_by_table: dict[str, int],
) -> dict[str, Any]:
    """Return fail-closed blockers from already measured active counts."""

    active_vector_tables = [
        table_name for table_name, count in active_vector_rows_by_table.items() if count > 0
    ]
    return {
        "active_retrieval_profiles": active_retrieval_profiles,
        "active_vector_rows_by_table": active_vector_rows_by_table,
        "vector_tables_with_rows": active_vector_tables,
        "has_blockers": bool(active_retrieval_profiles or active_vector_tables),
    }


def collect_blockers(*, dsn: str, idx_vec_tables: list[str]) -> dict[str, Any]:
    """Measure live blockers against PostgreSQL."""

    import psycopg2
    from psycopg2.extensions import parse_dsn

    connection = psycopg2.connect(**parse_dsn(dsn))
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM retrieval_profiles WHERE active = true")
            active_retrieval_profiles = int(cursor.fetchone()[0])
            active_vector_rows_by_table: dict[str, int] = {}
            for table_name in idx_vec_tables:
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table_name} WHERE is_active = true"  # noqa: S608
                )
                active_vector_rows_by_table[table_name] = int(cursor.fetchone()[0])
    finally:
        connection.close()
    return blockers_from_counts(
        active_retrieval_profiles=active_retrieval_profiles,
        active_vector_rows_by_table=active_vector_rows_by_table,
    )


def dry_run_report(
    *,
    repo_root: Path,
    inventory_before: dict[str, Any],
    blockers: dict[str, Any],
) -> dict[str, Any]:
    """Build the non-destructive reset plan."""

    filesystem_targets = summarize_filesystem(derived_paths(repo_root))
    confirmation_token = build_confirmation_token(
        inventory_before=inventory_before,
        filesystem_targets=filesystem_targets,
    )
    return {
        "mode": "dry_run",
        "status": "blocked" if blockers["has_blockers"] else "planned",
        "delete_tables_in_order": list(DELETE_TABLES_IN_ORDER),
        "filesystem_targets": filesystem_targets,
        "blockers": blockers,
        "inventory_before": inventory_before,
        "inventory-before": inventory_before,
        "confirmation_token": confirmation_token,
    }


def _assert_within_repo(path: Path, *, repo_root: Path) -> None:
    """Fail closed if a derived path escapes the workspace root."""

    resolved = path.resolve()
    root = repo_root.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"refusing to delete path outside repo root: {resolved}")


def _delete_filesystem(paths: list[Path], *, repo_root: Path) -> None:
    """Delete derived filesystem roots after verifying containment."""

    for path in paths:
        _assert_within_repo(path, repo_root=repo_root)
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def _delete_tables(cursor: Any, *, inventory_before: dict[str, Any]) -> dict[str, int]:
    """Delete derived PostgreSQL rows in FK-safe order."""

    deleted: dict[str, int] = {}
    for table_name in inventory_before.get("idx_vec_tables", []):
        cursor.execute(f"DELETE FROM {table_name}")  # noqa: S608 - table comes from inventory
        deleted[table_name] = int(cursor.rowcount)
    for table_name in DELETE_TABLES_IN_ORDER:
        cursor.execute(f"DELETE FROM {table_name}")  # noqa: S608 - allowlisted constant
        deleted[table_name] = int(cursor.rowcount)
    return deleted


def apply_reset(
    *,
    repo_root: Path,
    dsn: str,
    inventory_before: dict[str, Any],
    blockers: dict[str, Any],
) -> dict[str, Any]:
    """Apply the derived-artifact reset after blocker checks pass."""

    if blockers["has_blockers"]:
        return {
            "mode": "apply",
            "status": "blocked",
            "reason": "active_legacy_state_present",
            "blockers": blockers,
            "inventory_before": inventory_before,
            "inventory-before": inventory_before,
        }

    import psycopg2
    from psycopg2.extensions import parse_dsn

    connection = psycopg2.connect(**parse_dsn(dsn))
    try:
        with connection:
            with connection.cursor() as cursor:
                deleted_rows = _delete_tables(cursor, inventory_before=inventory_before)
        _delete_filesystem(derived_paths(repo_root), repo_root=repo_root)
    finally:
        connection.close()

    inventory_after = collect_inventory(dsn)
    return {
        "mode": "apply",
        "status": "applied",
        "deleted_rows": deleted_rows,
        "filesystem_targets": summarize_filesystem(derived_paths(repo_root)),
        "inventory_before": inventory_before,
        "inventory-before": inventory_before,
        "inventory_after": inventory_after,
        "inventory-after-reset": inventory_after,
    }


def main() -> int:
    args = parse_args()
    env = dict(load_env_file(Path(args.env_file)))
    env.update(os.environ)
    dsn = build_dsn_from_env(env)
    if not dsn:
        payload = {"status": "blocked", "reason": "postgres_dsn_missing"}
        print(json.dumps(payload, indent=2 if not args.json else None, ensure_ascii=False))
        return 2

    inventory_before = collect_inventory(dsn)
    blockers = collect_blockers(dsn=dsn, idx_vec_tables=inventory_before.get("idx_vec_tables", []))
    filesystem_targets = summarize_filesystem(derived_paths(REPO_ROOT))
    expected_confirmation_token = build_confirmation_token(
        inventory_before=inventory_before,
        filesystem_targets=filesystem_targets,
    )
    if args.apply and not args.confirm_token:
        payload = {
            "mode": "apply",
            "status": "blocked",
            "reason": "confirmation_token_required",
            "next_step": "run_dry_run_and_copy_confirmation_token",
        }
        print(json.dumps(payload, indent=2 if not args.json else None, ensure_ascii=False))
        return 1
    if args.apply and args.confirm_token != expected_confirmation_token:
        payload = {
            "mode": "apply",
            "status": "blocked",
            "reason": "confirmation_token_mismatch",
            "next_step": "rerun_dry_run_and_use_the_latest_confirmation_token",
        }
        print(json.dumps(payload, indent=2 if not args.json else None, ensure_ascii=False))
        return 1
    report = (
        apply_reset(
            repo_root=REPO_ROOT,
            dsn=dsn,
            inventory_before=inventory_before,
            blockers=blockers,
        )
        if args.apply
        else dry_run_report(
            repo_root=REPO_ROOT,
            inventory_before=inventory_before,
            blockers=blockers,
        )
    )
    print(json.dumps(report, indent=2 if not args.json else None, ensure_ascii=False))
    return 0 if report["status"] in {"planned", "applied"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
