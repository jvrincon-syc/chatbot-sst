# ADR-009: Aislamiento por proyecto (tenant) en el runtime de retrieval

Date: 2026-08-19

## Status

Accepted. Extiende [ADR-006](ADR-006-rag-platform-project-variant-release.md)
(identidades de plataforma), [ADR-005](ADR-005-postgres-pgvector-profile-separation.md)
(tablas `idx_vec_*` separadas por perfil de embedding, **compartidas** entre
proyectos) y [ADR-008](ADR-008-pure-platform-project-ownership-not-null.md)
(`project_id` NOT NULL en toda la cadena derivada, dedup scoped por proyecto). El
backfill de §Decision-3 está condicionado a un probe read-only en vivo
(fail-closed si la procedencia no es determinista).

## Context

ADR-008 dejó bien el **almacenamiento**: `project_id` NOT NULL en `idx_vec_*`,
`indexing_nodes`, `embedding_bundles`, etc., con unicidad y FKs compuestas por
`(project_id, ...)`. Cada fila de vector/nodo lleva su dueño de proyecto.

El **runtime de retrieval**, en cambio, no usa esa dimensión:

- `RetrievalProfile` (`retrieval/domain/models.py`) **no contiene `project_id`**;
  solo `consumer_scope_type/id`, `corpus_version`, `embedding_profile_id`,
  `indexing_target_id`. El servicio de retrieval no tiene un tenant key canónico
  que propagar al SQL.
- `PostgresVectorSearch.search` filtra por `is_active + embedding_profile_id +
  indexing_target_id + corpus_version`, **sin `project_id`**; los JOIN a
  `indexing_nodes` / `indexing_normalized_documents` tampoco lo incluyen.
- `PostgresLexicalSearch.search` filtra por `node_role='child' + corpus_version +
  FTS`, sin `project_id` ni `indexing_target_id`.
- `PostgresParentExpansion.expand` filtra por `node_id ANY + node_role='parent' +
  corpus_version`. El `node_id` es un id físico namespaced por proyecto (ADR-007),
  así que la expansión hereda aislamiento **solo si** los child nodes que la
  siembran vinieron de una búsqueda ya aislada — cosa que hoy no ocurre.
- `PostgresVectorRepository.activate_bundle` / `rollback_to_bundle` /
  `count_active_rows` operan por `embedding_profile_id + indexing_target_id +
  corpus_version + document_id`, **sin `project_id`**.

Como las `idx_vec_*` son tablas físicas **compartidas por perfil de embedding**
(no por proyecto, ADR-005/008) y un mismo documento físico puede pertenecer
deliberadamente a dos proyectos, dos proyectos que compartan una combinación
compatible `(embedding_profile, indexing_target, corpus_version)`:

```text
Project A ─┐
           ├── misma lane física de retrieval
Project B ─┘
```

pueden (a) **recuperar evidencia mutua** y (b) **desactivarse filas activas entre
sí** al activar/rollbackear un bundle. El SQL **no puede demostrar aislamiento**
porque el tenant key no participa en la consulta. Para una plataforma
multi-proyecto es un blocker P0.

No hay evidencia de fuga en la BD viva: el probe pre-Fase 7 observó un único
proyecto (`proj_sst-general`). El defecto es **arquitectónico**: la garantía no es
demostrable y se rompe en cuanto aterriza un 2.º proyecto que comparta lane.

## Decision

1. **`RetrievalProfile` gana `project_id` (identidad de plataforma, NOT NULL).** Es
   el tenant key canónico que el servicio de retrieval propaga. Se persiste en
   `retrieval_profiles` (migración versionada; bump de schema del artefacto).

2. **`project_id` se propaga de extremo a extremo y participa en TODA consulta de
   la lane**, fail-closed:

   ```text
   RetrievalProfile.project_id
         ↓
   RetrievalSearchRequest / SearchRetrievalUseCase
         ↓
   VectorSearchPort / LexicalSearchPort / ParentExpansionPort
         ↓
   Postgres adapters:  AND vector_row.project_id = %s
                       AND node.project_id = %s
         ↓
   activate_bundle / rollback_to_bundle / count_active_rows / readiness
                       AND project_id = %s
   ```

   Un perfil sin `project_id`, o un adapter al que no se le pase, **no puede
   recuperar ni activar/desactivar** (se abstiene). El `node_id` namespaced por
   proyecto (ADR-007) queda como defensa en profundidad **secundaria**; el filtro
   explícito `project_id` es la frontera primaria demostrable en SQL.

3. **Backfill de `retrieval_profiles` existentes — determinista o bloquea.** El
   `project_id` de un perfil se deriva del dueño de sus vectores activos
   `(embedding_profile_id, indexing_target_id, corpus_version)`:
   - exactamente **1** proyecto propietario en esas filas → backfill determinista;
   - **N** proyectos (lane compartida) → es precisamente la fuga: **BLOQUEA**
     (fail-closed) y se resuelve con dev reset (ADR-007) o migración con evidencia
     revisada; **prohibido** adivinar el proyecto;
   - **0** filas (perfil sin vectores) → perfil huérfano; se decide por operador.

   La rama aplicable se confirma con un probe **read-only** en vivo antes de correr
   la migración de enforcement. Con un único proyecto vivo hoy, el caso es la rama
   determinista.

4. **El contrato HTTP observable de `/api/retrieval` no expone tablas físicas** ni
   cambia su forma de respuesta; `project_id` es una identidad lógica de plataforma.

## Consequences

- El aislamiento por proyecto pasa a ser **demostrable en SQL**: ninguna consulta
  de retrieval/activación cruza proyectos.
- `RetrievalProfile` gana un campo requerido; los puertos de vector/lexical/parent
  search, activación, rollback, count y readiness cambian de firma (project_id).
  Adaptadores in-memory y Postgres se actualizan juntos, con contract tests.
- Migración versionada en `retrieval_profiles` + backfill condicionado (§3).
- La creación de perfiles de retrieval debe recibir `project_id` (del release/
  variante de plataforma que los origina), no solo `consumer_scope`.
- Publicar una release sigue **sin** activar retrieval legacy (invariante de Fase 6
  intacto); esta ADR endurece la lane para cuando el multi-proyecto se exponga.

## Alternatives considered

- **Confiar solo en el `node_id` namespaced (ADR-007).** Rechazada: las consultas
  clave por `(profile, target, corpus)` (vector search WHERE, activación, lexical)
  no son por `node_id`, así que el namespacing no las aísla.
- **Un `indexing_target` físico por proyecto (tabla `idx_vec_*` por proyecto).**
  Rechazada: contradice ADR-005/008 (tablas compartidas por perfil de embedding) y
  multiplica almacenamiento/DDL sin necesidad; el `project_id` por fila ya existe.
- **Filtrar solo vector search.** Rechazada: activación/rollback/count y lexical
  también cruzan proyectos; el fix debe ser de extremo a extremo.
