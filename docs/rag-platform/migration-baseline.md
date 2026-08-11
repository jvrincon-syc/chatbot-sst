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

## Inventario PostgreSQL real

Recolectado con `scripts/rag_platform/inventory_baseline.py` contra la base
declarada (`chatbot_sst`, local). El script es de **solo lectura**, resuelve el
DSN con `build_dsn_from_env` (`SST_POSTGRES_DSN`/`DATABASE_URL`, sin inventar
credenciales) y no aplica ninguna migración. Regenerar y verificar:

```bash
export SST_POSTGRES_DSN="postgresql://postgres@localhost:5432/chatbot_sst"
npm run python -- scripts/rag_platform/inventory_baseline.py          # Markdown
npm run python -- scripts/rag_platform/inventory_baseline.py --json   # JSON completo (incluye not-null)
```

El *digest de contenido* es independiente del orden de filas: hashea cada fila
(`md5(t.*::text)`) y agrega los hashes ordenados, de modo que dos bases con el
mismo contenido producen el mismo valor. `d41d8cd9…` es el md5 del conjunto
vacío (tabla sin filas).

<!-- INVENTORY:BEGIN (salida verbatim del script; no editar a mano) -->
### Inventario de baseline (corrida real)

- Servidor: `PostgreSQL 18.4 on x86_64-windows, compiled by msvc-19.44.35227, 64-bit`
- Tablas `idx_vec_*`: idx_vec_llama_bge_m3_v1, idx_vec_llama_cohere_embed_v4_v1, idx_vec_llama_first_local_v1, idx_vec_llama_voyage_4_v1, idx_vec_local_bge_m3_v1, idx_vec_local_cohere_embed_v4_v1, idx_vec_local_voyage_4_v1

| Tabla | Filas | Digest de contenido |
| --- | ---: | --- |
| `indexing_normalized_documents` | 39 | `7ad80b33674ad9760c37ba1e3ead74ca` |
| `chunk_bundles` | 40 | `b97552ad2dc5b10109fef294dcd26776` |
| `embedding_bundles` | 15 | `381b512e9c9a8a6c5909de7a5fa74028` |
| `embedding_runs` | 9 | `13698c0fa7eab6dd46deb8ca46680d48` |
| `indexing_runs` | 2 | `a46b1efc694116149caafe01305213e5` |
| `indexing_nodes` | 24 | `a00a2e46acd1c039e159174ce16353b2` |
| `retrieval_profiles` | 1 | `2945a0f85ffbcf75805d9aaf9e1df05f` |
| `idx_vec_llama_bge_m3_v1` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `idx_vec_llama_cohere_embed_v4_v1` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `idx_vec_llama_first_local_v1` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `idx_vec_llama_voyage_4_v1` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `idx_vec_local_bge_m3_v1` | 18 | `c8b1193afcf5c5abcaef03e548ee8901` |
| `idx_vec_local_cohere_embed_v4_v1` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `idx_vec_local_voyage_4_v1` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |

#### Constraints e índices reales por tabla

- `chunk_bundles`
  - constraints: chunk_bundles_child_count_check (check), chunk_bundles_parent_count_check (check), chunk_bundles_status_check (check), chunk_bundles_source_document_id_fkey (foreign_key), chunk_bundles_pkey (primary_key), chunk_bundles_bundle_fingerprint_key (unique)
  - índices: chunk_bundles_bundle_fingerprint_key, chunk_bundles_pkey, idx_chunk_bundles_corpus_profile, idx_chunk_bundles_source_document
- `embedding_bundles`
  - constraints: embedding_bundle_status_complete (check), embedding_bundles_configuration_fingerprint_check (check), embedding_bundles_dimension_check (check), embedding_bundles_distance_metric_check (check), embedding_bundles_legacy_status_explicit (check), embedding_bundles_readiness_status_check (check), embedding_bundles_status_check (check), embedding_bundles_validation_status_check (check), embedding_bundles_vector_count_check (check), embedding_bundles_embedding_profile_id_fkey (foreign_key), embedding_bundles_source_chunk_bundle_id_fkey (foreign_key), embedding_bundles_pkey (primary_key), embedding_bundles_source_chunk_bundle_id_embedding_profile__key (unique)
  - índices: embedding_bundles_pkey, embedding_bundles_source_chunk_bundle_id_embedding_profile__key, idx_embedding_bundles_one_ready_snapshot, idx_embedding_bundles_profile_corpus, idx_embedding_bundles_source_chunk_bundle
- `embedding_runs`
  - constraints: embedding_runs_configuration_fingerprint_check (check), embedding_runs_request_fingerprint_check (check), embedding_runs_runtime_mode_check (check), embedding_runs_status_check (check), embedding_runs_embedding_profile_id_fkey (foreign_key), embedding_runs_produced_bundle_fk (foreign_key), embedding_runs_source_chunk_bundle_id_fkey (foreign_key), embedding_runs_pkey (primary_key), embedding_runs_idempotency_key_request_fingerprint_key (unique)
  - índices: embedding_runs_idempotency_key_request_fingerprint_key, embedding_runs_pkey, idx_embedding_runs_idempotency_key, idx_embedding_runs_profile_status, idx_embedding_runs_source_chunk_bundle
- `indexing_nodes`
  - constraints: indexing_nodes_check (check), indexing_nodes_ingestion_origin_check (check), indexing_nodes_node_role_check (check), indexing_nodes_source_hash_check (check), indexing_nodes_document_id_fkey (foreign_key), indexing_nodes_parent_self_fk (foreign_key), indexing_nodes_source_chunk_bundle_fk (foreign_key), indexing_nodes_pkey (primary_key)
  - índices: idx_indexing_nodes_corpus, idx_indexing_nodes_document, idx_indexing_nodes_metadata, idx_indexing_nodes_parent, idx_indexing_nodes_source_chunk_bundle, indexing_nodes_pkey
- `indexing_normalized_documents`
  - constraints: indexing_normalized_documents_ingestion_origin_check (check), indexing_normalized_documents_processing_status_check (check), indexing_normalized_documents_source_hash_check (check), indexing_normalized_documents_pkey (primary_key), indexing_normalized_documents_document_id_source_hash_corpu_key (unique)
  - índices: indexing_normalized_documents_document_id_source_hash_corpu_key, indexing_normalized_documents_pkey
- `indexing_runs`
  - constraints: indexing_runs_activation_status_valid (check), indexing_runs_config_hash_check (check), indexing_runs_status_check (check), indexing_runs_validation_status_valid (check), indexing_runs_embedding_bundle_fk (foreign_key), indexing_runs_embedding_profile_fk (foreign_key), indexing_runs_profile_id_fkey (foreign_key), indexing_runs_target_fk (foreign_key), indexing_runs_pkey (primary_key)
  - índices: idx_indexing_runs_embedding_bundle, idx_indexing_runs_idempotency_request, idx_indexing_runs_target_corpus, indexing_runs_pkey
- `retrieval_profiles`
  - constraints: retrieval_profiles_last_runtime_status_check (check), retrieval_profiles_validation_status_check (check), retrieval_profiles_embedding_profile_id_fkey (foreign_key), retrieval_profiles_indexing_target_id_fkey (foreign_key), retrieval_profiles_pkey (primary_key)
  - índices: idx_retrieval_profiles_one_active_scope_corpus, idx_retrieval_profiles_profile_target, idx_retrieval_profiles_verified_active_scope_corpus, retrieval_profiles_pkey
<!-- INVENTORY:END -->

Nota de verificación de nombres: los constraints/índices reales coinciden con
los definidos en los `.sql` del baseline (p. ej. la unicidad legacy
`chunk_bundles_bundle_fingerprint_key` y `indexing_normalized_documents_document_id_source_hash_corpu_key`),
confirmando que este entorno no diverge de los archivos. Fases 0-2 no ejecutan
migración destructiva ni backfill; las migraciones con backfill (Fases 4+) deben
re-ejecutar este inventario y anexar la salida antes de retirar cualquier
unicidad global.
