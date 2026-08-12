# ADR-008: Pure-platform — `project_id` NOT NULL de raw a indexing y retiro de la lane legacy

Date: 2026-08-12

## Status

Accepted. Supersede parcialmente [ADR-007](ADR-007-phase4-physical-ownership-and-hard-reset.md)
(decisiones §1 "nullable mientras coexista legacy", §9/D1 "no retirar unicidad
global" y §2 "dual-mode legacy byte-idéntico"). Extiende
[ADR-006](ADR-006-rag-platform-project-variant-release.md). Alcance: cierre
operativo de Fase 4 sobre una BD **vacía** (hard reset ejecutado por el usuario el
2026-08-12).

## Context

ADR-007 mantuvo `project_id` nullable, conservó la unicidad global
`chunk_bundles_bundle_fingerprint_key` y añadió un camino dual-mode legacy porque
existían datos de prueba vivos (18 vectores, 15 bundles, 24 nodos) que un
tightening a NOT NULL habría roto, y porque retirar la unicidad global exigía
backup restaurable probado.

Ese supuesto **ya no aplica**: el usuario ejecutó un hard reset y la BD está
**vacía, sin ninguna fila legacy**. Mantener `project_id` nullable, la unicidad
global y el dual-mode legacy en este estado es complejidad muerta: protege datos
que no existen y deja abierto el hueco que Fase 4 quería cerrar (que un artefacto
nazca sin dueño de proyecto). La plataforma RAG multi-proyecto es ahora el **único**
modelo de datos hacia adelante.

## Decision

1. **`project_id` NOT NULL en toda la cadena derivada**, de raw a indexing:
   `chunk_bundles`, `embedding_bundles`, `indexing_nodes`, las 7 `idx_vec_*`,
   `embedding_runs`, `indexing_runs` e `indexing_materializations`. Ningún artefacto
   derivado puede nacer sin dueño de proyecto. `rag_variant_id`/`rag_release_id`
   siguen **nullable sin FK** (la release es de Fase 5; un rebuild de Fase 4 corre
   con solo `project_id`).

2. **Retiro de la unicidad global** `chunk_bundles_bundle_fingerprint_key`
   (supersede ADR-007 §9/D1). La dedup pasa a ser **scoped por proyecto**:
   `UNIQUE(project_id, bundle_fingerprint)`. Dos proyectos pueden compartir el mismo
   `bundle_fingerprint` sin colisión; ya no hace falta traducir
   `UniqueViolation → CrossProjectLegacyFingerprintCollision` para ese caso (el
   error de dominio queda como salvaguarda, sin ruta que lo dispare en el flujo
   pure-platform). No se requiere backup porque no hay datos que migrar.

3. **Retiro progresivo de la lane legacy** (supersede ADR-007 §2 dual-mode). El
   camino `project_id IS NULL` (node_id == chunk_id byte-idéntico, bypass MATCH
   SIMPLE) deja de ser un modo soportado. Se retira **por capas** (dominio →
   aplicación → adaptadores → scripts), ajustando las pruebas que asumían el
   default legacy, no en un solo big-bang. Hasta que una capa se limpie, su rama
   legacy queda inalcanzable en runtime porque la BD rechaza `project_id NULL`.

4. **Guard de purga en la migración de tightening**: antes de `SET NOT NULL`, la
   migración `20260810_08` borra en orden FK-safe cualquier fila `project_id IS
   NULL` de las tablas derivadas (incluidas las que fabrica el backfill legacy
   `20260805_14`). Esto hace la migración idempotente y consistente sin editar
   migraciones históricas ya aplicadas en otros entornos. En la BD vacía actual es
   un no-op.

5. **Sin cambio en el resto de ADR-007**: identidad física namespaced (§2 parte
   física), lifecycle de materialización `WRITING→SEALED|FAILED` (§3), storage
   sellado por proyecto (§4), SST dormido Fase 4–8 (§8) y `corpus_version` NOT NULL
   como marcador (§6) se mantienen. `corpus_version` se evaluará por separado.

## Consequences

- Un artefacto derivado sin `project_id` es imposible a nivel de BD: el aislamiento
  de proyecto es total, no "solo para filas de plataforma".
- Se elimina el punto de bifurcación legacy/plataforma; menos ramas, menos pruebas
  dobles, menos superficie de error. La lane legacy de retrieval (`/api/retrieval`,
  `is_active`) sigue intacta como consumidor separado hasta su reconexión (Fase 9);
  lo que se retira es la **escritura** derivada legacy.
- Deuda declarada: las ramas de código legacy se retiran por capas (no todo en este
  ADR); mientras tanto quedan inalcanzables por la restricción de BD. El CLI de la
  lane de plataforma (`chunk→embed→index→materializa`) sigue pendiente para el
  end-to-end vivo.
- Riesgo: re-aplicar `prepare-postgres` tras poblar `indexing_normalized_documents`
  volvería a correr el backfill legacy `20260805_14`; la purga de la §4 lo neutraliza
  en `08`, pero el backfill debe dejar de fabricar filas legacy en una limpieza
  posterior de la cadena de migraciones.

## Orden de trabajo

DDL de tightening (`20260810_08`) → retiro de ramas legacy por capa con sus pruebas
→ CLI de rebuild de plataforma → end-to-end vivo. Detalle en
`plans/2026-08-11-fase4-embedding-nodos-vectores.md`.
