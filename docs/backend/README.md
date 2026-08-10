# Operacion backend

## 1. Purpose and scope

Este README es la vista transversal del backend versionado en la rama actual.
Resume como se conectan `ingestion`, `chunking`, `embedding`, `indexing`,
`retrieval`, `observability`, `core`, `api` y los CLIs operativos. No sustituye
los READMEs por area: los enlaza y deja claro el recorrido extremo a extremo.

## 2. Current branch state

En `HEAD` conviven dos superficies backend:

- una superficie local/GUI de ingesta basada en
  `app.back.src.ingestion.gui.server`;
- una superficie HTTP bundle-first basada en FastAPI en
  [app.py](../../app/back/src/api/app.py) para `embedding`, `indexing` y
  `retrieval`.

La rama comprometida ya llega hasta evidencia recuperable, readiness y perfiles
durables. No contiene todavia una capa final versionada de respuesta/chat SST
por encima de `retrieval`.

## 3. Code map

- [../../app/back/src/ingestion](../../app/back/src/ingestion): inventario,
  lectura, OCR, parsing, normalizacion, clasificacion, extraccion, validacion y
  promocion.
- [../../app/back/src/chunking](../../app/back/src/chunking): construccion
  parent-child, validacion y superficie HTTP local.
- [../../app/back/src/embedding](../../app/back/src/embedding): perfiles,
  corridas, bundles, readiness y registry de engines.
- [../../app/back/src/indexing](../../app/back/src/indexing): indexacion
  bundle-first en memoria o PostgreSQL/pgvector.
- [../../app/back/src/retrieval](../../app/back/src/retrieval): perfiles,
  validacion, vector search, lexical fallback y expansion de parents.
- [../../app/back/src/core](../../app/back/src/core): feature flags, consumer
  scope, logging estructurado y sanitizacion de observabilidad.
- [../../app/back/src/api](../../app/back/src/api): composicion FastAPI y
  wiring compartido.
- [../../scripts](../../scripts): entrypoints CLI reales para operadores,
  validacion, preparacion y smoke checks.

## 4. Inputs and outputs

Entradas principales:

- `data/docs_raw` o un staging root para ingesta.
- `data/docs_normalized` y sus manifests para chunking y validacion downstream.
- chunk bundles para embedding.
- embedding bundles y perfiles verificados para indexing.
- retrieval profiles, targets activos y queries para retrieval.

Salidas principales:

- artefactos normalizados Schema 2.0 y `_manifests/`;
- chunk bundles y manifests de ejecucion;
- embedding bundles y readiness checks;
- indexing runs, nodes y vector rows activas;
- evidencia recuperable y estado durable de perfiles/readiness.

## 5. Operational flow

El flujo observable es:

```text
docs_raw
  -> ingestion
  -> docs_normalized + manifests
  -> chunking
  -> chunk bundles
  -> embedding
  -> embedding bundles + readiness
  -> indexing
  -> targets/nodes/vectors
  -> retrieval
  -> evidencia recuperable
```

El detalle de handoffs y gates esta en
[phase-handoffs.md](./phase-handoffs.md).

## 6. Rules and invariants

- `data/docs_raw` es fuente original inmutable; no es el contrato operativo
  editable.
- `data/docs_normalized` es el contrato compartido principal entre Fase 1 y el
  resto del pipeline.
- Los flags se leen en el composition root; dominio y application no deben leer
  entorno directamente.
- `promote_candidate` solo exige validacion estructural aprobada; las decisiones
  manuales de review pertenecen a workflows operativos, no al gate tecnico de
  promocion actual.
- La composicion bundle-first no acepta una tabla vectorial arbitraria en el
  request: resuelve perfil, target y persistence lane desde contratos durables.
- Retrieval no debe inventar evidencia ni responder por fuera del corpus
  aprobado.

## 7. Critical variables and configuration

- `SST_FEATURE_EMBEDDING_V2`, `SST_FEATURE_INDEXING_BUNDLE_FIRST` y
  `SST_FEATURE_RETRIEVAL_V1` gobiernan la exposicion bundle-first.
- `SST_PERSISTENCE_MODE` y `SST_POSTGRES_DSN` deciden lane `memory` o
  `postgres`.
- `SST_CONSUMER_SCOPE_TYPE` y `SST_CONSUMER_SCOPE_ID` fijan el scope durable de
  activacion.
- `OCR_*`, `TESSERACT_*`, `OCRMYPDF_CMD` y `GHOSTSCRIPT_CMD` afectan la calidad
  de ingesta local.
- `LLAMA_*` controla la ruta experimental/cloud de parse, classify y extract.
- `EMBEDDING_*`, `HF_*`, `BGE_*` y `VOYAGE_API_KEY` definen runtime de
  embeddings.

La matriz ampliada esta en [critical-variables.md](./critical-variables.md).

## 8. Logs, manifests, and observability

- `_manifests/` bajo `data/docs_normalized` conserva inventario, validacion y
  reportes de corridas.
- `readiness_checks`, `indexing_runs` y perfiles durables registran estado de
  lanes bundle-first.
- La observabilidad redacted y los eventos canonicos se describen en
  [../observability/current-contracts.md](../observability/current-contracts.md).
- No se deben registrar chunks completos, queries sensibles, vectores, secretos
  ni payloads crudos de proveedores.

## 9. Commands and verification

```powershell
npm run test:ingestion
npm run python -- -m pytest app/back/tests/chunking -v
npm run test:embedding
npm run test:indexing
npm run test:retrieval
```

Antes de tocar una fase especifica, conviene abrir su README operativo y sus
comandos locales de smoke/verify.

## 10. Visible inconsistencies and debt

- La GUI heredada y FastAPI siguen fragmentando la superficie HTTP total.
- Hay concentracion de complejidad en `ingestion/pipeline.py`,
  `ingestion/gui/server.py`, `api/dependencies.py` y
  `scripts/indexing/run_indexing.py`.
- La navegacion documental historica sigue repartida entre `README.md`,
  `docs/README.md`, `CLAUDE.md`, `memory/` y `plans/`.
- Redis aparece en configuracion compartida, pero no como lane operativo central
  comparable a PostgreSQL o filesystem.

El detalle esta en [gaps-and-debt.md](./gaps-and-debt.md).

## 11. Missing pieces to reach the target model

- Unificar mas la superficie HTTP entre GUI heredada y API bundle-first.
- Reducir concentracion de logica en entrypoints grandes si el equipo decide
  atacar deuda de codigo, no solo deuda documental.
- Completar la historia versionada desde `retrieval` hasta una respuesta final
  verificable de chatbot SST cuando esa capa exista en esta rama.
- Terminar de separar documentacion canonica versionada de notas locales o
  historicas que hoy aun conviven en carpetas paralelas.

## 12. References

- [phase-handoffs.md](./phase-handoffs.md)
- [critical-variables.md](./critical-variables.md)
- [gaps-and-debt.md](./gaps-and-debt.md)
- [../ingestion/README.md](../ingestion/README.md)
- [../chunking/README.md](../chunking/README.md)
- [../embedding/README.md](../embedding/README.md)
- [../indexing/README.md](../indexing/README.md)
- [../retrieval/README.md](../retrieval/README.md)
- [../llama_first/README.md](../llama_first/README.md)
- [../observability/README.md](../observability/README.md)
