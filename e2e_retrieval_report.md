# Reporte end-to-end plataforma RAG (local, BGE-M3)

- Generado: 2026-08-14T15:52:28.267434+00:00
- Proyecto: `proj_sst-general`
- Variante: `ragv_local-bge`
- Documentos: convivencia_laboral/manual/introduccion.md, convivencia_laboral/manual/1761580555950_syc_RE.RH-04SST23102025.pdf, convivencia_laboral/manual/1781045303349_syc_politicadedesconexin.pdf

## Persistencia de identidad

- **project_id** `proj_sst-general`: PERSISTIDO — 3 chunk_bundles, 3 embedding_bundles, 21 indexing_nodes, 16 vectores, 2 materializaciones (todos namespaced por proyecto).
- **rag_variant_id** `ragv_local-bge`: PERSISTIDO (provenance) — en 3/3 chunk_bundles; embedding_runs.rag_variant_id = ['ragv_local-bge'].
- **rag_release_id**: NULL — NO persistido — este flujo (rebuild materializa artefactos físicos) no construye una release; el rag_release_id se crea en la fase de release (corpus snapshot + CreateDraft/Validate), pendiente con los 2 documentos extra.

## Motor de embedding (recipe)

- provider `bge` · model `BAAI/bge-m3` · dimensión 1024 · métrica `cosine` · normalización `l2`
- La dimensión/modelo/métrica/normalización viven en el **perfil de embedding** (recurso global, ADR-005); cambiarlos crea otro perfil y por tanto otra variante RAG. 1024 es la dimensión nativa de BGE-M3 (no es parámetro libre del motor).

## Retrieval — 6 preguntas, top_k=6 (vectores materializados, cosine, embedding de query BGE-M3)

### ¿Qué es el comité de convivencia laboral?

| # | score | rol | sección | chunk (snippet) |
|---|-------|-----|---------|-----------------|
| 1 | 0.5984 | child |  | - Garantizar los mecanismos y medios para que los trabajadores, puedan  presentar queja frente a la' posible vulneración de este derecho. Tener en cuenta que lo |
| 2 | 0.5179 | child |  | Es importante que existan unas normas de convivencia claras que permitan regular las relaciones que se dan al interior de la empresa, evitando con ello que se a |
| 3 | 0.4691 | child |  | plimiento de lo dispuesto por la ley 2191 de 2022, Sistemas y computadores a la Política de Desconexión laboral, la cual está alineada con el compromiso mpañía, |
| 4 | 0.4559 | child |  | PROCESOS ADMINISTRATIVOS / SEGURIDAD Y SALUD EN EL TRABAJO POLÍTICA DE DESCONEXION LABORAL NIVEL DE "CODIGO PL.RH-035ST \| CLASIFICACIÓN \| USO INTERNO (NC2) Y  |
| 5 | 0.4153 | child |  | \| POLÍTICA DE DESCONEXIÓN LABORAL UN |
| 6 | 0.4139 | child |  | QUEJAS: Si va a presentar una queja, diligencie la opción 1. SUGERENCIAS: Si va a presentar una sugerencia diligencie la opción 2.  1. QUEJAS  Si usted quiere p |

### ¿Cuáles son las funciones del comité de convivencia?

| # | score | rol | sección | chunk (snippet) |
|---|-------|-----|---------|-----------------|
| 1 | 0.5205 | child |  | - Garantizar los mecanismos y medios para que los trabajadores, puedan  presentar queja frente a la' posible vulneración de este derecho. Tener en cuenta que lo |
| 2 | 0.5187 | child |  | Es importante que existan unas normas de convivencia claras que permitan regular las relaciones que se dan al interior de la empresa, evitando con ello que se a |
| 3 | 0.4188 | child |  | FORMATO PARA INTERPONER QUEJA POR PRESUNTO ACOSO ANTE EL COMITÉ DE CONVIVENCIA. RE.RH-04 NIVEL DE USO INTERNO CÓDIGO Versión |
| 4 | 0.4188 | child |  | FORMATO PARA INTERPONER QUEJA POR PRESUNTO ACOSO ANTE EL COMITÉ DE CONVIVENCIA. RE.RH-04 NIVEL DE USO INTERNO CÓDIGO Versión |
| 5 | 0.3752 | child |  | plimiento de lo dispuesto por la ley 2191 de 2022, Sistemas y computadores a la Política de Desconexión laboral, la cual está alineada con el compromiso mpañía, |
| 6 | 0.3579 | child |  | 0.3  SST CLASIFICACIÓN (NC2)  RELACIÓN DE LOS HECHOS CONSTITUTIVOS DE LA QUEJA: Deben incluirse todos los elementos en los que se identifiquen las circunstancia |

### ¿En qué consiste la política de desconexión laboral?

| # | score | rol | sección | chunk (snippet) |
|---|-------|-----|---------|-----------------|
| 1 | 0.7432 | child |  | \| POLÍTICA DE DESCONEXIÓN LABORAL UN |
| 2 | 0.6924 | child |  | PROCESOS ADMINISTRATIVOS / SEGURIDAD Y SALUD EN EL TRABAJO POLÍTICA DE DESCONEXION LABORAL NIVEL DE "CODIGO PL.RH-035ST \| CLASIFICACIÓN \| USO INTERNO (NC2) Y  |
| 3 | 0.6469 | child |  | plimiento de lo dispuesto por la ley 2191 de 2022, Sistemas y computadores a la Política de Desconexión laboral, la cual está alineada con el compromiso mpañía, |
| 4 | 0.5597 | child |  | - Garantizar los mecanismos y medios para que los trabajadores, puedan  presentar queja frente a la' posible vulneración de este derecho. Tener en cuenta que lo |
| 5 | 0.4972 | child |  | Entorpecimiento Laboral: Toda acción tendiente a obstaculizar el cumplimiento de una labor o hacerla más gravosa o retardarla con perjuicio para el trabajador.  |
| 6 | 0.4312 | child |  | QUEJAS: Si va a presentar una queja, diligencie la opción 1. SUGERENCIAS: Si va a presentar una sugerencia diligencie la opción 2.  1. QUEJAS  Si usted quiere p |

### ¿Cómo se presentan quejas o denuncias de convivencia?

| # | score | rol | sección | chunk (snippet) |
|---|-------|-----|---------|-----------------|
| 1 | 0.5824 | child |  | FORMATO PARA INTERPONER QUEJA POR PRESUNTO ACOSO ANTE EL COMITÉ DE CONVIVENCIA. RE.RH-04 NIVEL DE USO INTERNO CÓDIGO Versión |
| 2 | 0.5824 | child |  | FORMATO PARA INTERPONER QUEJA POR PRESUNTO ACOSO ANTE EL COMITÉ DE CONVIVENCIA. RE.RH-04 NIVEL DE USO INTERNO CÓDIGO Versión |
| 3 | 0.5744 | child |  | - Garantizar los mecanismos y medios para que los trabajadores, puedan  presentar queja frente a la' posible vulneración de este derecho. Tener en cuenta que lo |
| 4 | 0.5589 | child |  | Es importante que existan unas normas de convivencia claras que permitan regular las relaciones que se dan al interior de la empresa, evitando con ello que se a |
| 5 | 0.5393 | child |  | 0.3  SST CLASIFICACIÓN (NC2)  RELACIÓN DE LOS HECHOS CONSTITUTIVOS DE LA QUEJA: Deben incluirse todos los elementos en los que se identifiquen las circunstancia |
| 6 | 0.5344 | child |  | QUEJAS: Si va a presentar una queja, diligencie la opción 1. SUGERENCIAS: Si va a presentar una sugerencia diligencie la opción 2.  1. QUEJAS  Si usted quiere p |

### ¿Qué normas de convivencia deben cumplir los trabajadores?

| # | score | rol | sección | chunk (snippet) |
|---|-------|-----|---------|-----------------|
| 1 | 0.7059 | child |  | Es importante que existan unas normas de convivencia claras que permitan regular las relaciones que se dan al interior de la empresa, evitando con ello que se a |
| 2 | 0.6142 | child |  | - Garantizar los mecanismos y medios para que los trabajadores, puedan  presentar queja frente a la' posible vulneración de este derecho. Tener en cuenta que lo |
| 3 | 0.5530 | child |  | plimiento de lo dispuesto por la ley 2191 de 2022, Sistemas y computadores a la Política de Desconexión laboral, la cual está alineada con el compromiso mpañía, |
| 4 | 0.5237 | child |  | PROCESOS ADMINISTRATIVOS / SEGURIDAD Y SALUD EN EL TRABAJO POLÍTICA DE DESCONEXION LABORAL NIVEL DE "CODIGO PL.RH-035ST \| CLASIFICACIÓN \| USO INTERNO (NC2) Y  |
| 5 | 0.4851 | child |  | QUEJAS: Si va a presentar una queja, diligencie la opción 1. SUGERENCIAS: Si va a presentar una sugerencia diligencie la opción 2.  1. QUEJAS  Si usted quiere p |
| 6 | 0.4596 | child |  | \| POLÍTICA DE DESCONEXIÓN LABORAL UN |

### ¿Cuál es el objetivo del reglamento del comité de convivencia?

| # | score | rol | sección | chunk (snippet) |
|---|-------|-----|---------|-----------------|
| 1 | 0.5566 | child |  | Es importante que existan unas normas de convivencia claras que permitan regular las relaciones que se dan al interior de la empresa, evitando con ello que se a |
| 2 | 0.5174 | child |  | - Garantizar los mecanismos y medios para que los trabajadores, puedan  presentar queja frente a la' posible vulneración de este derecho. Tener en cuenta que lo |
| 3 | 0.4340 | child |  | FORMATO PARA INTERPONER QUEJA POR PRESUNTO ACOSO ANTE EL COMITÉ DE CONVIVENCIA. RE.RH-04 NIVEL DE USO INTERNO CÓDIGO Versión |
| 4 | 0.4340 | child |  | FORMATO PARA INTERPONER QUEJA POR PRESUNTO ACOSO ANTE EL COMITÉ DE CONVIVENCIA. RE.RH-04 NIVEL DE USO INTERNO CÓDIGO Versión |
| 5 | 0.4120 | child |  | plimiento de lo dispuesto por la ley 2191 de 2022, Sistemas y computadores a la Política de Desconexión laboral, la cual está alineada con el compromiso mpañía, |
| 6 | 0.3922 | child |  | PROCESOS ADMINISTRATIVOS / SEGURIDAD Y SALUD EN EL TRABAJO POLÍTICA DE DESCONEXION LABORAL NIVEL DE "CODIGO PL.RH-035ST \| CLASIFICACIÓN \| USO INTERNO (NC2) Y  |
