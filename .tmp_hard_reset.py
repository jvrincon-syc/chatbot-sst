"""Hard reset one-off del pipeline: filas Postgres + artefactos de embedding en disco.

No versionado. Borra DATOS y ARTEFACTOS generados, no esquema ni fuentes:
  - TRUNCATE tablas de datos (embedding / vectores fisicos / indexing / retrieval).
  - Borra data/embeddings/<bundle_id>/ (bundles sellados) para poder re-embeddear;
    el artifact store rechaza sobrescribir sellados ("sealed ... already exist").
Conserva: indexing_profiles/targets (config), catalogo normalizado, data/docs_raw,
data/docs_normalized y los artefactos de chunking (fuente de los chunk bundles).
"""
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "indexing"))

from prepare_postgres_indexing import build_dsn_from_env, load_env_file  # noqa: E402
import psycopg2  # noqa: E402
from psycopg2.extensions import parse_dsn  # noqa: E402

TABLES = [
    "readiness_checks",
    "retrieval_profiles",
    "indexing_materializations",
    "indexing_run_documents",
    "indexing_runs",
    "indexing_nodes",
    "embedding_bundle_chunks",
    "embedding_bundles",
    "embedding_runs",
    "chunk_bundles",
    "idx_vec_llama_first_local_v1",
    "idx_vec_local_bge_m3_v1",
    "idx_vec_llama_bge_m3_v1",
    "idx_vec_local_voyage_4_v1",
    "idx_vec_llama_voyage_4_v1",
    "idx_vec_local_cohere_embed_v4_v1",
    "idx_vec_llama_cohere_embed_v4_v1",
]

# 1) Postgres
dsn = build_dsn_from_env(load_env_file(Path("secrets.env")))
if not dsn:
    raise SystemExit("no DSN: define SST_POSTGRES_DSN / POSTGRES_* / DATABASE_URL en secrets.env")
conn = psycopg2.connect(**parse_dsn(dsn))
try:
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name = ANY(%s)",
                (TABLES,),
            )
            present = [r[0] for r in cur.fetchall()]
            if present:
                cur.execute(
                    "TRUNCATE TABLE "
                    + ", ".join(f'"{t}"' for t in present)
                    + " RESTART IDENTITY CASCADE"
                )
            print("db truncated:", len(present), "tablas")
finally:
    conn.close()

# 2) Artefactos de embedding en disco (data/embeddings/*). Se conserva el dir raiz.
embeddings_root = ROOT / "data" / "embeddings"
removed = 0
if embeddings_root.exists():
    for child in embeddings_root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed += 1
print("embedding artifacts removed:", removed, "entradas en", embeddings_root)
