# ADR-007: Fase 4 — propiedad física por proyecto, node_id namespaced y hard reset de artefactos derivados

Date: 2026-08-11

## Status

Accepted. Alcance: Fase 4 del plan de plataforma RAG multi-proyecto
(`docs/superpowers/plans/Plan_Ajustado_Plataforma_RAG_MultiProyecto(2).md`).
Extiende [ADR-006](ADR-006-rag-platform-project-variant-release.md). Aditivo sobre
la lane legacy; no retira constraints globales (eso queda para una migración
futura aprobada aparte).

## Context

Fase 4 debe hacer que embeddings, nodos y vectores físicos sean propiedad del
proyecto y no puedan colisionar entre proyectos. El estado real (Gate 0,
2026-08-11) es un entorno de **desarrollo, no producción**: `chatbot_sst` tiene
solo datos de prueba (18 vectores en `idx_vec_local_bge_m3_v1`, 15 embedding
bundles, 56 chunk_bundles, 24 nodos), y existe respaldo de `raw`/`normalized`.
El texto original de Fase 4 propone un backfill de `project_id` que deja filas
sin evidencia como `legacy_unverified`; para datos de prueba esa maquinaria es
complejidad sin retorno.

Además, `project_id` como columna simple no impide referencias cruzadas (un
vector de A apuntando a un embedding bundle de B) si los FKs son simples.

## Decision

1. **Aislamiento impuesto por la BD con claves/FKs compuestas**, no solo por
   validación en Python. Cada artefacto derivado lleva `project_id` y una unicidad
   compuesta usable como destino de FK:
   - `chunk_bundles`: `UNIQUE(project_id, chunk_bundle_id)`.
   - `embedding_bundles`: `UNIQUE(project_id, embedding_bundle_id)` +
     `FK(project_id, source_chunk_bundle_id) → chunk_bundles(project_id, chunk_bundle_id)`.
   - `indexing_nodes`: `UNIQUE(project_id, node_id)` +
     `FK(project_id, source_chunk_bundle_id) → chunk_bundles(project_id, chunk_bundle_id)`.
   - `idx_vec_*`: `FK(project_id, embedding_bundle_id) → embedding_bundles(...)` y
     `FK(project_id, node_id) → indexing_nodes(...)`; se mantiene
     `UNIQUE(embedding_bundle_id, node_id)`; `rag_release_id` **no** vive en la fila
     vectorial.
   - `indexing_materializations`: `FK(project_id, embedding_bundle_id) → embedding_bundles(...)`.

   Como `project_id` es **nullable**, Postgres (MATCH SIMPLE) no aplica el FK
   compuesto cuando es NULL: las filas legacy lo *bypassean* (usan su FK legacy) y
   solo las de plataforma quedan blindadas. `project_id` se mantiene nullable
   mientras la lane legacy coexista; no se hace *tightening* a NOT NULL en Fase 4.

2. **`node_id` físico namespaced** = `physical_node_id(project_id,
   source_chunk_bundle_id, source_chunk_id)` (hash de representación canónica
   etiquetada). Para filas de plataforma, `node_id` se separa de `source_chunk_id`
   (evidencia). El **padre de expansión es físico**: `parent_node_id =
   physical_node_id(project_id, source_chunk_bundle_id, source_parent_chunk_id)`,
   distinto de `source_parent_chunk_id` (evidencia). La expansión parent→child usa
   `parent_node_id`, nunca `source_parent_chunk_id`. La lane legacy conserva
   `node_id == source_chunk_id` byte-idéntico (default seguro, gated por
   `project_id IS NULL`); los 18 vectores legacy vivos no se tocan por migración.

3. **Materialización con lifecycle inmutable**: `WRITING → SEALED | FAILED`. Una
   materialización `SEALED` es inmutable (no cambian vectores, checksum ni
   conteos). El puerto expone `find_sealed`/`begin_writing`/`seal`/`mark_failed`,
   nunca `upsert` sobre una materialización sellada. Identidad
   `UNIQUE(project_id, embedding_bundle_id, indexing_target_id, storage_schema_version)`;
   campos `materialization_id`, `status`, `canonical_checksum`,
   `parent_node_count`/`child_node_count`/`vector_count`, timestamps y
   `failure_code`.

4. **Storage físico de embeddings por proyecto**, sellado y content-addressed:
   `data/projects/{project_id}/embeddings/{embedding_bundle_id}/` con
   `manifest.json`, artefacto de vectores y `checksums.json`. Se implementa un
   `SealedEmbeddingStore` (`stage`/`seal`/`read`/`verify_checksum`, nunca
   `replace`) que **reutiliza `core.atomic_fs`** y espeja `SealedChunkStore`
   (Fase 3). El nombre concreto del archivo de vectores sale del código real, no
   se inventa.

5. **Hard reset de artefactos derivados en vez de backfill.** Por ser datos de
   dev con respaldo de fuentes, Fase 4 **borra y reconstruye** los artefactos
   derivados (KEEP/RESET en el plan §Gate 0) en vez de inferir `project_id` sobre
   filas legacy. El reset se ejecuta con una herramienta
   `reset_derived_rag_artifacts` con `--dry-run`/`--apply` e inventario
   before/after; nunca borra `raw`, `normalized`, proyectos, perfiles ni
   configuración, y se niega a borrar filas referenciadas por un `retrieval_profile`
   activo / `is_active`. Todo artefacto reconstruido nace con `project_id`.

6. **`corpus_version` se mantiene NOT NULL** poblado con un marcador legacy en
   filas de plataforma, fuera de la identidad física (que la fijan los índices
   parciales). No se hace `DROP NOT NULL`.

7. **Runs no fabrican contexto de release.** `embedding_runs`/`indexing_runs`
   ganan `project_id`/`rag_variant_id`/`rag_release_id` como columnas **nullable
   sin FK** (la tabla `rag_releases` es de Fase 5). El servidor los deriva desde un
   build context validado; nunca se aceptan del payload del cliente. La API legacy
   no inventa contexto de release.

8. **SST queda dormido durante Fase 4–8.** El rebuild es platform-only y **no
   activa** vectores ni cambia `is_active`/`retrieval_profiles`; el retrieval
   legacy de SST no sirve hasta que una fase posterior (bootstrap `sst-general` +
   wiring de consumidor) lo reconecte. Confirmado por el usuario (2026-08-11).

9. **No se retira ninguna unicidad global en Fase 4** (ver ADR-006 y decisión D1).
   Si dos proyectos colisionan en el `bundle_fingerprint` global legacy, el
   adaptador traduce el `UniqueViolation` a un error de dominio
   `CrossProjectLegacyFingerprintCollision` y falla cerrado: nunca reutiliza,
   renombra ni borra el artefacto del otro proyecto. Verificado en BD que solo
   `chunk_bundles.bundle_fingerprint` es global; el `UNIQUE` de `embedding_bundles`
   ya incluye `source_chunk_bundle_id` y no bloquea el caso multi-proyecto. El
   retiro futuro de la unicidad global de `chunk_bundles` será una migración
   separada con backup restaurable probado, simulación sobre copia y aprobación
   explícita.

## Consequences

- Aislamiento cross-proyecto imposible de violar por referencia (lo impone la BD),
  no solo por convención en código.
- El rebuild limpio evita arrastrar identidad legacy ambigua; todo lo derivado
  nace con `project_id`.
- Costo: una unicidad compuesta "redundante" por tabla (destino de FK) y un punto
  de bifurcación legacy/plataforma que debe estar cubierto por pruebas de ambos
  caminos.
- Deuda explícita: retiro de la unicidad global de `chunk_bundles` (migración
  futura aprobada); reconexión del consumidor SST (fase posterior); `project_id`
  no se endurece a NOT NULL mientras la lane legacy coexista.

## Orden de trabajo

Diseño/código: dominio → puertos/aplicación → adaptadores → composition root.
Despliegue: Gate 0 → DDL aditivo → código dual-mode → reset controlado → rebuild
limpio → validación → habilitación. Detalle en el plan de Fase 4
(`plans/2026-08-11-fase4-embedding-nodos-vectores.md`).
