# Decision Log: Local Chunking Refactor

## 2026-07-23 - Task 0 baseline on `llamaparse_experiment`

### Scope

- Plan source: `memory/plan-chunking-local-ajustado.md`
- Working branch: `llamaparse_experiment`
- Workspace mode: direct edits on the current branch and workspace by user request

### Confirmed current implementation

- The active parser is
  [`structure_aware.py`](../../app/back/src/indexing/infrastructure/llama_index/node_parsers/structure_aware.py).
- The current algorithm iterates over `document.metadata["page_catalog"]`,
  creates one parent node per page, and then creates child nodes by splitting
  parent text with `max_child_chars`.
- There is no explicit overlap policy or overlap metadata between consecutive
  child nodes in the active implementation.
- [`pipeline_factory.py`](../../app/back/src/indexing/infrastructure/llama_index/pipeline_factory.py)
  composes `NormalizedDocumentFactory -> StructureAwareNodeParser ->
  MetadataEnrichmentPipeline` inside `LlamaIndexingPort`.
- [`document_factory.py`](../../app/back/src/indexing/infrastructure/llama_index/document_factory.py)
  adapts normalized bundles into a LlamaIndex `Document` and builds the current
  `page_catalog`.
- [`element_adapter.py`](../../app/back/src/indexing/infrastructure/llama_index/node_parsers/element_adapter.py)
  is a facade over the same parser, so it must keep delegating to the
  transformed implementation instead of preserving a divergent algorithm.

### Confirmed current consumers

- Direct production consumers found with `rg`:
  - `app/back/src/indexing/infrastructure/llama_index/pipeline_factory.py`
  - `app/back/src/indexing/infrastructure/llama_index/node_parsers/element_adapter.py`
- Direct test coverage found with `rg`:
  - `app/back/tests/indexing/node_parsers/test_parent_child_relationships.py`
  - `app/back/tests/indexing/infrastructure/test_ingestion_pipeline.py`
  - `app/back/tests/indexing/infrastructure/test_document_factory.py`

### HTTP composition status on this branch

- No `FastAPI` app or `APIRouter` composition point exists today under
  `app/back/src`.
- The only current HTTP server found in backend code is
  [`server.py`](../../app/back/src/ingestion/gui/server.py), which uses
  `ThreadingHTTPServer` for the ingestion GUI.
- Consequence: Task 7 cannot "plug into" an existing FastAPI composition point
  on this branch as written. We must first define the backend HTTP composition
  point without weakening the plan's requirement for thin API routes.

### Tokenizer decision for the refactor

- `tiktoken` is already available in the environment as version `0.13.0`.
- Decision: use a canonical tokenizer backed by `tiktoken` and version it explicitly in the chunking module instead of introducing a new dependency or any Torch-backed requirement.
- Rationale:
  - already installed in this branch environment;
  - deterministic and local;
  - no additional cloud dependency;
  - satisfies the plan restriction against adding Torch as a chunking requirement.

### Baseline verification captured before refactor

- The focused indexing baseline passed before the refactor using a
  workspace-local pytest basetemp to avoid Windows temp permission issues.
- Broader suite caveats recorded before refactor:
  - `app/back/tests/indexing -q` and `app/back/tests/ingestion -q` were
    initially blocked by `PermissionError` on the user temp directory.
  - A rerun with workspace-local `--basetemp` improved visibility, but pytest
    cleanup and some tmp-path-dependent ingestion tests still surfaced
    environment-level permission failures.
  - These environmental failures must not be attributed to the chunking
    refactor unless reproduced in focused chunking tests.

### Branch-vs-plan differences recorded before implementation

- The plan assumes a FastAPI composition point that does not yet exist on this branch.
- The parser integration point is confirmed and singular in indexing, which supports the requested strategy of transforming existing chunking code rather than layering a second active pipeline on top of it.
- The current node contracts are still page-oriented (`page_number`, `char_start`, `char_end`, `parent_node_id`), so the refactor must preserve compatibility while migrating the active algorithm toward semantic parent-child chunking.

## 2026-07-24 - Task 7 HTTP contract closure

### Implemented decisions

- A standalone FastAPI composition point was introduced under `app/back/src/chunking/api/app.py` because no backend FastAPI app existed on this branch.
- The HTTP layer remains thin: request validation and error translation stay in `api`, while execution, persistence, and chunk inspection remain in `application` and `infrastructure`.
- Chunking runs now execute outside the request path through a single-worker `ThreadPoolExecutor`, with the run manifest persisted before scheduling.
- The public contract now exposes typed OpenAPI schemas for profiles, runs, paginated run documents, validation, parents, children, and the uniform error envelope.
- `Idempotency-Key` is required and invalid or missing values return `422` through the uniform error model.

### Explicit known follow-ups

- Run manifests are persisted, but in-memory run state and idempotency indexes are not reconstructed after process restart.
- Parents and children inspection endpoints still return full lists without pagination.
- `GET /documents/{document_id}/parents?run_id=...` validates the run but does not select historical artifacts scoped to that run.

## 2026-07-24 - Task 8 corpus validation closure

### Implemented decisions

- A reusable validator was added in `scripts/chunking/validate_chunks.py` to validate:
  - the synthetic golden dataset;
  - deterministic rerun reuse on identical inputs;
  - OpenAPI export;
  - the invariant that `docs_normalized` remains unchanged.
- A versioned synthetic golden contract was added in `docs/chunking/golden_corpus_expected.json` and exercised by `app/back/tests/chunking/corpus/test_chunking_corpus_golden.py`.
- Real-corpus validation was executed against the 44 `processed` inventory records present on Friday, July 24, 2026, with `docs_normalized` unchanged and OpenAPI exported locally.

### Corrective decision from real-corpus validation

- Real-corpus validation surfaced an invariant failure on `convivencia_laboral/manual/normas_convivencia.md`: oversized children could be emitted when a long list parent was treated as atomic and when the final continuous-chunk merge ignored `unique_maximum`.
- The fix was applied in `ChildChunkBuilder` by:
  - removing list-driven forced atomic fallback for oversized parents;
  - preventing the final undersized-tail merge when it would exceed the unique-token maximum.
- A new regression test now covers long list parents to ensure all emitted children stay within `child_max_tokens`.

## 2026-07-28 - Task 9 operational closure

### Implemented decisions

- `ChunkingRunService` now rehydrates persisted `*.api-run.json` manifests on startup, so previously queued or running chunking runs come back as `interrupted` instead of disappearing after a restart.
- Persisted run manifests now carry the original `idempotency_key` and `payload_fingerprint`, which lets the service rebuild the idempotency index after a restart.
- `GET /api/chunking/documents/{document_id}/parents` and `GET /api/chunking/parents/{parent_id}/children` now expose paginated responses with `page`, `page_size`, `total_items`, and `total_pages`.
- Regression tests now cover restart hydration, idempotency conflict detection after reload, and paginated parent/child inspection.

## 2026-08-06 - Golden `parent_count` realignment for body-less root headings

### Problem

`test_chunking_corpus_golden.py::test_validate_chunks_recorre_golden_y_exporta_openapi`
failed with `parent_count mismatch for golden_manual_headings`. The golden
`docs/chunking/golden_corpus_expected.json` expected one more parent than the
chunker produces for three cases: `golden_manual_headings` (3→2),
`golden_reglamento_articulos` (4→3) and `golden_mixto_ruido` (3→2).

### Root cause (documented before touching the golden)

All three failing cases share the same shape: a root `# Title` heading with no
body of its own, immediately followed by sibling `##` sections.
`ParentChunkBuilder._merge_heading_only_sections`
(`app/back/src/chunking/application/parent_chunk_builder.py`) deliberately folds
a body-less heading section into the following section, so it never becomes its
own parent. A document with a body-less root `# Title` plus N `##` siblings
therefore yields N parents, not N+1.

This behavior is intentional and pinned by the unit contract
`test_parent_chunk_builder.py::test_fusiona_heading_sin_cuerpo_con_siguiente_seccion`
(7/7 unit tests green), whose scenario (`ÍNDICE` H1 without body → `1. CAPÍTULO`
H2) is identical to `# Manual SST` → `## Objetivo`. The remaining seven golden
cases already matched the chunker exactly.

### Decision

The chunker has **no regression**; it matches its unit contract. The **golden
fixture was stale** for the three body-less-root-heading cases — it encoded the
pre-merge assumption "root title = its own parent". The golden expectations
(and the paired `child_count_min` for `golden_reglamento_articulos`) were
corrected to the merge semantics; the chunker and its merge rule were left
unchanged. Bumped the golden `schema_version` to `1.1` and added an inline
`_contract` note plus per-case `_note` fields so the semantics travel with the
fixture. This is a documented contract correction, not a green-forcing edit.
