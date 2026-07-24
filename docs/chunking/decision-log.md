# Decision Log: Local Chunking Refactor

## 2026-07-23 - Task 0 baseline on `llamaparse_experiment`

### Scope

- Plan source: `memory/plan-chunking-local-ajustado.md`
- Working branch: `llamaparse_experiment`
- Workspace mode: direct edits on the current branch and workspace by user request

### Confirmed current implementation

- The active parser is [`app/back/src/indexing/infrastructure/llama_index/node_parsers/structure_aware.py`](/C:/Users/jvrincon/Documents/chatbot_sst/chatbot-sst/app/back/src/indexing/infrastructure/llama_index/node_parsers/structure_aware.py).
- The current algorithm iterates over `document.metadata["page_catalog"]`, creates one parent node per page, and then creates child nodes by splitting parent text with `max_child_chars`.
- There is no explicit overlap policy or overlap metadata between consecutive child nodes in the active implementation.
- [`app/back/src/indexing/infrastructure/llama_index/pipeline_factory.py`](/C:/Users/jvrincon/Documents/chatbot_sst/chatbot-sst/app/back/src/indexing/infrastructure/llama_index/pipeline_factory.py) composes `NormalizedDocumentFactory -> StructureAwareNodeParser -> MetadataEnrichmentPipeline` inside `LlamaIndexingPort`.
- [`app/back/src/indexing/infrastructure/llama_index/document_factory.py`](/C:/Users/jvrincon/Documents/chatbot_sst/chatbot-sst/app/back/src/indexing/infrastructure/llama_index/document_factory.py) adapts normalized bundles into a LlamaIndex `Document` and builds the current `page_catalog`.
- [`app/back/src/indexing/infrastructure/llama_index/node_parsers/element_adapter.py`](/C:/Users/jvrincon/Documents/chatbot_sst/chatbot-sst/app/back/src/indexing/infrastructure/llama_index/node_parsers/element_adapter.py) is a facade over the same parser, so it must keep delegating to the transformed implementation instead of preserving a divergent algorithm.

### Confirmed current consumers

- Direct production consumers found with `rg`:
  - `app/back/src/indexing/infrastructure/llama_index/pipeline_factory.py`
  - `app/back/src/indexing/infrastructure/llama_index/node_parsers/element_adapter.py`
- Direct test coverage found with `rg`:
  - `app/back/tests/indexing/node_parsers/test_parent_child_relationships.py`
  - `app/back/tests/indexing/infrastructure/test_ingestion_pipeline.py`
  - `app/back/tests/indexing/infrastructure/test_document_factory.py`

### HTTP composition status on this branch

- No `FastAPI` app or `APIRouter` composition point exists today under `app/back/src`.
- The only current HTTP server found in backend code is [`app/back/src/ingestion/gui/server.py`](/C:/Users/jvrincon/Documents/chatbot_sst/chatbot-sst/app/back/src/ingestion/gui/server.py), which uses `ThreadingHTTPServer` for the ingestion GUI.
- Consequence: Task 7 cannot "plug into" an existing FastAPI composition point on this branch as written. We must first define the backend HTTP composition point without weakening the plan's requirement for thin API routes.

### Tokenizer decision for the refactor

- `tiktoken` is already available in the environment as version `0.13.0`.
- Decision: use a canonical tokenizer backed by `tiktoken` and version it explicitly in the chunking module instead of introducing a new dependency or any Torch-backed requirement.
- Rationale:
  - already installed in this branch environment;
  - deterministic and local;
  - no additional cloud dependency;
  - satisfies the plan restriction against adding Torch as a chunking requirement.

### Baseline verification captured before refactor

- Relevant indexing baseline executed successfully en una corrida historica previa a fijar el workspace a `C:\venvs\chatbot-sst`:
  - `.\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/indexing/node_parsers/test_parent_child_relationships.py app/back/tests/indexing/infrastructure/test_document_factory.py app/back/tests/indexing/infrastructure/test_ingestion_pipeline.py -q --basetemp .\pytest-basetemp-indexing-focus`
  - Result: `10 passed` in the current workspace.
- Broader suite caveats recorded before refactor:
  - `app/back/tests/indexing -q` and `app/back/tests/ingestion -q` were initially blocked by `PermissionError` on `C:\Users\jvrincon\AppData\Local\Temp\pytest-of-jvrincon`.
  - A rerun with workspace-local `--basetemp` improved visibility, but `pytest` cleanup and some tmp-path-dependent ingestion tests still surfaced environment-level permission failures.
  - These environmental failures must not be attributed to the chunking refactor unless reproduced in focused chunking tests.

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
