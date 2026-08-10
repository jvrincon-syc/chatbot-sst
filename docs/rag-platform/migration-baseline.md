# Baseline de migración — plataforma RAG (Fase 0)

Manifiesto reproducible del estado desde el que arranca la plataforma. Este
documento es la autoridad técnica del baseline; los READMEs de área describen
estado histórico y no deben tratarse como baseline de plataforma.

## Commit y árbol

- **Baseline de referencia del plan:** `3bc9a8a` (10 de agosto de 2026).
- **HEAD al iniciar Fases 0-2:** `9784d2f` (dos commits por delante; ambos
  aditivos sobre el baseline, sin cambios de esquema).
- Los READMEs de área (`ingestion`, `chunking`, `embedding`, `indexing`,
  `retrieval`, `observability`, `llama_first`) citan `f918b51` en afirmaciones
  **históricas y acotadas** (p. ej. "no existía README de embedding en ese
  commit"). Reescribir ese hash volvería falsas esas frases. En su lugar, cada
  README apunta a este manifiesto como baseline de plataforma; el hash histórico
  se conserva por precisión.

## Migraciones aplicadas en el baseline (20 archivos)

Orden determinista por nombre (así las aplica
`scripts/indexing/prepare_postgres_indexing.py`). SHA-256 truncado a 16 hex por
archivo, calculado sobre el árbol de trabajo del baseline:

| sha256[:16] | archivo |
| --- | --- |
| 43b12b5bd5b73e4b | 20260721_create_llama_index_tables.sql |
| 857c8d7b7767ffdd | 20260722_indexing_profiles_pgvector.sql |
| 123098f3e0218d91 | 20260722_seed_indexing_profiles.sql |
| da39a8aeb2d395e7 | 20260805_01_extend_indexing_profiles.sql |
| 1e86ae5ebeb9b0db | 20260805_02_create_indexing_targets.sql |
| 6bd0bf23b0834973 | 20260805_03_backfill_indexing_targets.sql |
| b4c9007ec8bd8d5c | 20260805_04_create_chunk_bundles.sql |
| 6682733cb988cda3 | 20260805_05_create_embedding_runs.sql |
| ed2bc8a8d947fe7c | 20260805_06_create_embedding_bundles.sql |
| 233f0ac037e30f53 | 20260805_07_create_embedding_bundle_chunks.sql |
| a243390d0d7c8569 | 20260805_08_extend_indexing_runs.sql |
| 9da9b7b5ada954b2 | 20260805_09_complete_indexing_run_documents.sql |
| 9d53514e20412109 | 20260805_10_extend_indexing_nodes.sql |
| d714385d0acbc622 | 20260805_11_extend_idx_vec_tables.sql |
| 8488abce5a61f13f | 20260805_12_create_readiness_checks.sql |
| e6e4b48578414323 | 20260805_13_create_retrieval_profiles.sql |
| e72656a1c3116f15 | 20260805_14_backfill_legacy.sql |
| e03333c6e913c178 | 20260805_15_activate_strong_constraints.sql |
| db3b797c933c7751 | 20260805_16_add_embedding_profile_verification_check_kind.sql |
| 230781b10ade552a | 20260806_01_seed_bge_m3_semantic_revision.sql |

Regenerar y verificar el manifiesto:

```bash
for f in migrations/*.sql; do
  printf "%s  %s\n" "$(sha256sum "$f" | cut -c1-16)" "$(basename "$f")"
done
```

Las migraciones nuevas de plataforma (`20260810_01..03`) se ordenan tras
`20260806_01` y son `CREATE ... IF NOT EXISTS`, inocuas para legacy.

## Inventario PostgreSQL real — PENDIENTE OPERATIVO (requiere DSN)

El criterio de salida de Fase 0 pide conteos y hashes reales de
`indexing_normalized_documents`, `chunk_bundles`, `embedding_bundles`,
`embedding_runs`, `indexing_runs`, `indexing_nodes`, `idx_vec_*` y
`retrieval_profiles`, más la verificación de los nombres reales de constraints,
PKs e índices en la base que se migrará.

Esto **no se ejecutó**: no hay `SST_POSTGRES_DSN` disponible en el entorno de
desarrollo actual, y la política `fail-closed` prohíbe inventar cifras. Queda
como paso operativo. Procedimiento cuando exista DSN autorizado (no ejecutar
contra producción sin autorización registrada):

```sql
-- Conteos por tabla base del baseline.
SELECT 'indexing_normalized_documents' AS t, count(*) FROM indexing_normalized_documents
UNION ALL SELECT 'chunk_bundles', count(*) FROM chunk_bundles
UNION ALL SELECT 'embedding_bundles', count(*) FROM embedding_bundles
UNION ALL SELECT 'embedding_runs', count(*) FROM embedding_runs
UNION ALL SELECT 'indexing_runs', count(*) FROM indexing_runs
UNION ALL SELECT 'indexing_nodes', count(*) FROM indexing_nodes
UNION ALL SELECT 'retrieval_profiles', count(*) FROM retrieval_profiles;

-- Nombres reales de constraints/PK/índices (no asumir por los .sql).
SELECT conrelid::regclass AS tabla, conname, contype
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace
ORDER BY tabla, conname;
```

Registrar la salida (conteos + lista de constraints) en un anexo versionado de
este documento antes de cualquier migración con backfill (Fases 4+). Fases 0-2
no ejecutan migración destructiva ni backfill, por lo que no bloquean por este
pendiente, pero sí lo dejan declarado.
