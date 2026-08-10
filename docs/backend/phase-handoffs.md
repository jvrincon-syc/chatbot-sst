# Handoffs entre fases backend

## Propósito

Este documento describe cómo se transfiere el control y los datos entre las
fases operativas implementadas en la rama actual, desde `docs_raw` hasta
retrieval. La meta es dejar explícitos los contratos de entrada/salida, los
gates y los consumidores inmediatos.

## Flujo extremo a extremo

| Fase | Entrada principal | Transformación | Salida principal | Gate antes de pasar | Siguiente consumidor |
| --- | --- | --- | --- | --- | --- |
| Inventario/ingesta | `data/docs_raw` o ruta staging | fingerprint, lectura, OCR/parse, normalización, clasificación, extracción, validación | Markdown y artefactos Schema 2.0 + `_manifests/` en `data/docs_normalized` o staging | validación estructural y estado documental (`processed` o `needs_review`) | `chunking`, revisión humana, indexación filtrada |
| Revisión/promoción | candidate root + manifest de validación estructural | promoción controlada del candidato validado; `review_decisions.json` puede existir como soporte operativo, pero no es gate técnico actual | candidato promovido a `data/docs_normalized` | validación estructural aprobada | `chunking`, `indexing`, GUI |
| Chunking | `docs_normalized` aprobado | parser estructural + parent builder + child builder + validación | chunk bundles e índices de inspección | bundle válido y correlación con documento normalizado | `embedding`, inspección HTTP/GUI |
| Embedding | chunk bundle + perfil verificado | lectura de chunks, batch embedding, validación y readiness | embedding bundle + readiness checks | perfil compatible, motor disponible, documentos habilitados | `indexing` |
| Indexing | embedding bundle + perfil/target | construcción de nodos, persistencia de rows activas, activación/rollback | indexing runs, nodes, vector rows, targets activos | bundle listo, target compatible, persistencia confirmada si PostgreSQL | `retrieval` |
| Retrieval | retrieval profile + target activo + query | query embedding, vector search, lexical fallback, parent expansion | evidencia recuperada y estado de readiness/validación | perfil activo y validado; fallback léxico permitido si vector falla | capa de respuesta/chat futura o consumidor HTTP |

## Fase 1: `docs_raw` -> `docs_normalized`

### Entry points

- [run_pipeline.py](../../scripts/ingestion/run_pipeline.py)
- [server.py](../../app/back/src/ingestion/gui/server.py)
- [pipeline.py](../../app/back/src/ingestion/pipeline.py)

### Artefactos de salida

- `*.md`
- `*.metadata.json`
- `*.pages.json`
- `*.ocr.json`
- `*.tables.json`
- `*.forms.json`
- manifests bajo `_manifests/`

### Gate

- validación estructural por `validate_normalized_tree`
- warnings materiales o ausencia de evidencia crítica empujan a
  `needs_review`
- la promoción es atómica y separada de la normalización base
- `needs_review` no bloquea por sí solo `promote_candidate`; el gate real en
  `HEAD` es que la validación estructural haya pasado

## Fase 2: `docs_normalized` -> chunk bundles

### Entry points

- [app.py](../../app/back/src/chunking/api/app.py)
- [run_service.py](../../app/back/src/chunking/application/run_service.py)

### Salida

- bundles parent-child
- manifiestos `*.api-run.json`
- material de inspección y validación de chunking

### Gate

- el documento fuente debe existir en `docs_normalized`
- las referencias de spans y blocks deben ser coherentes con el documento
  normalizado

## Fase 3: chunk bundles -> embedding bundles

### Entry points

- `POST /api/embedding/runs` dentro de
  [router.py](../../app/back/src/embedding/api/router.py)
- [verify_profile.py](../../scripts/embedding/verify_profile.py)

### Salida

- corridas de embedding
- embedding bundles
- readiness checks

### Gate

- perfil de embedding verificado
- semántica del engine compatible con el perfil
- bundle de chunking vigente y elegible

## Fase 4: embedding bundles -> indexación durable o en memoria

### Entry points

- [run_indexing.py](../../scripts/indexing/run_indexing.py)
- `POST /api/indexing/runs` dentro de
  [router.py](../../app/back/src/indexing/api/router.py)

### Salida

- indexing runs
- nodos parent/child persistidos
- filas vectoriales activas
- activación o rollback del target

### Gate

- bundle de embeddings listo para indexación
- target compatible con el perfil
- `--persist-confirmed` y `SST_POSTGRES_DSN` cuando la persistencia real es
  PostgreSQL

## Fase 5: indexación -> retrieval

### Entry points

- `POST /api/retrieval/profiles`
- `POST /api/retrieval/profiles/{id}/activate`
- `POST /api/retrieval/profiles/{id}/validate`

### Salida

- readiness del lane de retrieval
- evidencia recuperada
- fallback léxico explícitamente observable

### Gate

- perfil de retrieval activo y validado
- filas vectoriales activas para el corpus/target/perfil
- si no hay vector search disponible, solo puede contestar el camino léxico si
  `lexical_fallback_policy` lo permite

## Superficies HTTP y CLI

El repo expone dos superficies distintas:

- **GUI/HTTP de ingesta**: `ingestion.gui.server` con bridge ASGI hacia parte de
  la API bundle-first.
- **FastAPI bundle-first**: [api/app.py](../../app/back/src/api/app.py) para
  `embedding`, `indexing` y `retrieval`.

Los CLIs siguen siendo la fuente más directa para inventario, pipeline,
preparación PostgreSQL, verificación de perfiles y benchmarks.

## Plataforma RAG: cuatro semánticas separadas (ADR-006)

La plataforma multi-proyecto introduce estados que **no** son sinónimos entre sí
ni de la activación legacy. El handoff entre fases debe preservar la distinción:

| Concepto | Confirma | No implica |
| --- | --- | --- |
| `promoted` | promoción técnica del normalizado (gate legacy: validación estructural) | que la revisión sea releaseable |
| `release_eligible` | la revisión puede entrar a un corpus snapshot | promoción ni publicación |
| `PUBLISHED` | el catálogo de plataforma acepta la release | activación de retrieval ni cambio de consumidor |
| activación legacy (`is_active`) | qué release consulta el chatbot | nada de lo anterior; no se toca en este plan |

Una revisión `needs_review` exige decisión de elegibilidad versionada antes de
entrar a un snapshot. Detalle en
[identity-and-reuse-contract.md](../rag-platform/identity-and-reuse-contract.md)
y baseline en [migration-baseline.md](../rag-platform/migration-baseline.md).

## Puntos de acoplamiento a vigilar

- La ingesta y la GUI comparten mucha orquestación en archivos grandes.
- El boundary entre GUI heredada y FastAPI bundle-first existe, pero no
  unifica toda la operación backend.
- `docs_normalized` sigue siendo el contrato compartido más importante entre
  Fase 1 y el resto del pipeline.
