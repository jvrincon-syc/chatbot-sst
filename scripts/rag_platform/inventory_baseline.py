"""Inventario de baseline pre-migración para la plataforma RAG (Fase 0).

Recolecta, contra la PostgreSQL real, conteos y un digest de contenido
determinista de las tablas legacy que la plataforma evolucionará, más los
nombres reales de PK/constraints/índices. La salida es reproducible y sirve
como evidencia archivable en ``docs/rag-platform/migration-baseline.md``.

No inventa credenciales: reutiliza :func:`build_dsn_from_env` del script de
preparación de indexing. No aplica ninguna migración ni escribe en la base.

Uso:
    npm run python -- scripts/rag_platform/inventory_baseline.py [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "app" / "back" / "src"))
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "indexing"))

from prepare_postgres_indexing import build_dsn_from_env  # noqa: E402

# Tablas legacy que la plataforma evoluciona; el inventario las congela antes
# de cualquier migración de plataforma (plan §5 Fase 0).
INVENTORIED_TABLES: tuple[str, ...] = (
    "indexing_normalized_documents",
    "chunk_bundles",
    "embedding_bundles",
    "embedding_runs",
    "indexing_runs",
    "indexing_nodes",
    "retrieval_profiles",
)


def _table_digest(cursor: Any, table: str) -> dict[str, Any]:
    """Devuelve conteo y un digest de contenido independiente del orden.

    El digest hashea cada fila y agrega los hashes ordenados, de modo que dos
    bases con el mismo contenido producen el mismo valor sin depender del orden
    físico de las filas.
    """

    cursor.execute("SELECT to_regclass(%s)", (table,))
    if cursor.fetchone()[0] is None:
        return {"present": False, "count": 0, "content_digest": None}
    cursor.execute(f'SELECT COUNT(*) FROM "{table}"')  # noqa: S608 - nombre de allowlist
    count = int(cursor.fetchone()[0])
    cursor.execute(
        f'SELECT md5(COALESCE(string_agg(row_md5, \'\' ORDER BY row_md5), \'\'))'
        f' FROM (SELECT md5(t.*::text) AS row_md5 FROM "{table}" t) s'  # noqa: S608
    )
    return {"present": True, "count": count, "content_digest": cursor.fetchone()[0]}


def _table_constraints(cursor: Any) -> dict[str, list[dict[str, str]]]:
    cursor.execute(
        """
        SELECT c.relname AS table_name, con.conname AS name, con.contype AS kind
          FROM pg_constraint con
          JOIN pg_class c ON c.oid = con.conrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relname = ANY(%s)
         ORDER BY c.relname, con.contype, con.conname
        """,
        (list(INVENTORIED_TABLES),),
    )
    kinds = {
        "p": "primary_key",
        "u": "unique",
        "f": "foreign_key",
        "c": "check",
        "n": "not_null",
    }
    out: dict[str, list[dict[str, str]]] = {}
    for table_name, name, kind in cursor.fetchall():
        out.setdefault(table_name, []).append({"name": name, "kind": kinds.get(kind, kind)})
    return out


def _table_indexes(cursor: Any) -> dict[str, list[str]]:
    cursor.execute(
        """
        SELECT tablename, indexname FROM pg_indexes
         WHERE schemaname = 'public' AND tablename = ANY(%s)
         ORDER BY tablename, indexname
        """,
        (list(INVENTORIED_TABLES),),
    )
    out: dict[str, list[str]] = {}
    for table_name, index_name in cursor.fetchall():
        out.setdefault(table_name, []).append(index_name)
    return out


def collect_inventory(dsn: str) -> dict[str, Any]:
    """Recolecta el inventario completo en una sola conexión de solo lectura."""

    import psycopg2
    from psycopg2.extensions import parse_dsn

    connection = psycopg2.connect(**parse_dsn(dsn))
    try:
        with connection:  # read-only: commit no escribe nada
            with connection.cursor() as cursor:
                cursor.execute("SELECT version()")
                server_version = cursor.fetchone()[0]
                tables = {t: _table_digest(cursor, t) for t in INVENTORIED_TABLES}
                cursor.execute(
                    "SELECT tablename FROM pg_tables"
                    " WHERE schemaname='public' AND tablename LIKE 'idx_vec_%'"
                    " ORDER BY tablename"
                )
                idx_vec = [r[0] for r in cursor.fetchall()]
                for name in idx_vec:
                    tables[name] = _table_digest(cursor, name)
                constraints = _table_constraints(cursor)
                indexes = _table_indexes(cursor)
    finally:
        connection.close()
    return {
        "server_version": server_version,
        "idx_vec_tables": idx_vec,
        "tables": tables,
        "constraints": constraints,
        "indexes": indexes,
    }


def render_markdown(inventory: dict[str, Any]) -> str:
    lines = ["### Inventario de baseline (corrida real)", ""]
    lines.append(f"- Servidor: `{inventory['server_version'].splitlines()[0]}`")
    lines.append(f"- Tablas `idx_vec_*`: {', '.join(inventory['idx_vec_tables'])}")
    lines += ["", "| Tabla | Filas | Digest de contenido |", "| --- | ---: | --- |"]
    for name, info in inventory["tables"].items():
        digest = info["content_digest"] or "(vacía)"
        lines.append(f"| `{name}` | {info['count']} | `{digest}` |")
    lines += ["", "#### Constraints e índices reales por tabla", ""]
    for name in sorted(set(inventory["constraints"]) | set(inventory["indexes"])):
        # not_null se omite del render (queda en --json); domina la señal útil.
        cons = ", ".join(
            f"{c['name']} ({c['kind']})"
            for c in inventory["constraints"].get(name, [])
            if c["kind"] != "not_null"
        ) or "—"
        idxs = ", ".join(inventory["indexes"].get(name, [])) or "—"
        lines.append(f"- `{name}`")
        lines.append(f"  - constraints: {cons}")
        lines.append(f"  - índices: {idxs}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emitir JSON en vez de Markdown")
    args = parser.parse_args()

    dsn = build_dsn_from_env(os.environ)
    if not dsn:
        print(
            "No hay DSN: define SST_POSTGRES_DSN o DATABASE_URL (o POSTGRES_HOST/DB/USER).",
            file=sys.stderr,
        )
        return 2
    inventory = collect_inventory(dsn)
    print(json.dumps(inventory, indent=2) if args.json else render_markdown(inventory))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
