# ADR-006: Identidad de plataforma RAG (project / variant / release)

Date: 2026-08-10

## Status

Accepted. Alcance: Fases 0-2 del plan de plataforma RAG multi-proyecto
(`docs/superpowers/plans/Plan_Ajustado_Plataforma_RAG_MultiProyecto(2).md`).
Aditivo sobre la lane legacy bundle-first; no la modifica ni la retira.

## Context

El repo tiene hoy un corpus SST único cuya identidad documental depende solo de
`source_relpath` (`ingestion/paths.py:stable_document_id`). Eso impide:

- aislar varios proyectos que compartan la misma ruta relativa;
- reutilizar artefactos físicos exactos entre releases sin duplicarlos;
- distinguir una receta semántica (parseo/chunking/embedding) de un snapshot de
  corpus concreto.

El plan introduce tres responsabilidades separadas: `project_id` posee los
artefactos físicos, `rag_variant_id` identifica una receta semántica inmutable y
`rag_release_id` es un snapshot inmutable de una variante sobre un corpus. La
lane legacy (`Activation`, `Retrieval`, `retrieval_profiles`, `corpus_version`)
permanece intacta.

## Decision

1. **Identidades tipadas y no intercambiables.** Cada identidad lleva un prefijo
   validado (`proj_`, `ragv_`, `corpus_`, `ragr_`, `sdoc_`, `srev_`, `pp_`,
   `cp_`) y se materializa como `PlatformId` en
   `rag_platform/domain/identity.py`. Dos identidades de clase distinta nunca son
   iguales aunque compartan cuerpo, y construir un contexto con la clase
   equivocada falla cerrado (`InvalidIdentity`). Se elige `frozen dataclass` con
   `slots` para los contratos de identidad puros (sin dependencia de Pydantic) y
   `StrictModel` de Pydantic 2 para los modelos con persistencia/validación de
   campos (proyecto, variante, revisión, snapshot).

2. **La identidad nueva no depende solo de `source_relpath`.** Un documento de
   plataforma se identifica por `project_id + logical_document_id + revision`;
   la ruta queda como localizador versionado. `stable_document_id` legacy **no se
   modifica** (un test bloquea su hash exacto); la identidad nueva vive en
   `rag_platform`, sin tocar el contrato Schema 2.0 legacy.

3. **Semánticas distintas, documentadas.** Cuatro conceptos que hoy se confunden
   quedan separados y ninguno es sinónimo de otro:
   - `promoted`: la promoción técnica del artefacto normalizado terminó (gate
     legacy actual: validación estructural aprobada).
   - `release_eligible`: una revisión puede entrar a un corpus snapshot; una
     revisión `needs_review` exige una decisión de elegibilidad versionada
     (`approved_after_review`, `operator_waiver` o `blocked`) antes de entrar.
   - `PUBLISHED`: el catálogo de plataforma acepta la release; **no** activa
     retrieval ni cambia el consumidor legacy.
   - activación legacy (`ActivateIndexedBundleUseCase` / `is_active`): sigue
     siendo la única vía que cambia qué consulta el chatbot y no se toca.

4. **`corpus_version` es compatibilidad legacy.** No puede sustituir a
   `project_id`, `rag_variant_id`, `corpus_snapshot_id` ni `rag_release_id` en
   contratos nuevos.

5. **Reglas de creación:**
   - documento agregado/retirado/reemplazado ⇒ corpus snapshot nuevo ⇒ release
     nueva (no variante).
   - cambio semántico de parseo/normalización/chunking/embedding/perfil de
     recuperación ⇒ variante nueva y release nueva.
   - cambio de target físicamente compatible ⇒ release nueva, no variante.

## Alternatives Considered

1. **Extender los modelos Schema 2.0 legacy in situ** con campos `project_id`,
   `revision_id`, etc. Rechazada: los modelos son `StrictModel(extra="forbid")`
   y un test bloquea el hash de `stable_document_id`; mutarlos rompe golden files
   y contamina el contrato legacy con conceptos de plataforma.
2. **IDs como `str` planos** (como los tipa el borrador del plan). Rechazada
   como identidad única: no hace demostrable la no-intercambiabilidad en runtime.
   Se conserva `str` solo donde el ID cruza a un recurso global ya existente
   (`embedding_profile_id`, `indexing_target_id`).
3. **Modelos nuevos en `rag_platform` con adaptador legacy explícito**
   (seleccionada). Preserva el contrato legacy intacto y aísla la identidad
   nueva.

## Consequences

- Se crea el paquete `app/back/src/rag_platform/` con separación
  `domain/application/infrastructure`.
- Las migraciones `20260810_01..03` son `CREATE ... IF NOT EXISTS`, ordenadas
  tras `20260806_01`, e inocuas para legacy incluso antes de que exista el código
  de plataforma (las auto-aplica `prepare_postgres_indexing.py` por glob).
- El inventario PostgreSQL real y la verificación de nombres de constraints
  (criterio de salida de Fase 0) requieren `SST_POSTGRES_DSN` y quedan como paso
  operativo documentado en `docs/rag-platform/migration-baseline.md`, no como
  dato inventado.
- Ninguna decisión de esta ADR elimina o deshabilita endpoints, tablas, columnas
  o rutas legacy.
