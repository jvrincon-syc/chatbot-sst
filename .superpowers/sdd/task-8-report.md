# Task 8 Report

## Scope completed

- Added reusable validator script:
  - `scripts/chunking/validate_chunks.py`
- Added synthetic golden corpus contract:
  - `docs/chunking/golden_corpus_expected.json`
- Added golden corpus regression:
  - `app/back/tests/chunking/corpus/test_chunking_corpus_golden.py`
- Added API contract documentation:
  - `docs/chunking/api_contract.md`
- Updated implementation history and closure notes:
  - `docs/chunking/decision-log.md`

## Real-corpus validation

- Ran `validate_chunk_outputs(...)` against the current `data/docs_normalized` inventory.
- Eligible processed records on Friday, July 24, 2026: `44`
- Result:
  - `44` documents validated
  - `docs_normalized` unchanged
  - OpenAPI exported to `manual-test-temp/task8-real-corpus/openapi.json`
  - `19` documents emitted multiple children
  - `6` documents emitted multiple parents

## Corrective fix discovered during corpus validation

- Real corpus surfaced an invariant failure on `convivencia_laboral/manual/normas_convivencia.md`.
- Root cause:
  - oversized list-heavy parents could be forced through the atomic-child path;
  - the final continuous-chunk merge could exceed `unique_maximum`, causing a child above `child_max_tokens`.
- Fix applied in `app/back/src/chunking/application/child_chunk_builder.py`:
  - removed list-driven forced atomic fallback for oversized parents;
  - guarded the final undersized-tail merge so it only happens when the merged unique chunk still fits within `unique_maximum`.
- Added regression:
  - `test_lista_larga_no_se_trata_como_child_atomico`

## Verification

- Golden corpus test:
  - `c:\venvs\chatbot-sst\Scripts\python.exe -m pytest app/back/tests/chunking/corpus/test_chunking_corpus_golden.py -q --basetemp <workspace-temp>`
  - Result: `1 passed`

- Child-chunk regression suite:
  - `c:\venvs\chatbot-sst\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_child_chunk_builder.py -q --basetemp <workspace-temp>`
  - Result: `13 passed`

- Indexing regression:
  - `c:\venvs\chatbot-sst\Scripts\python.exe -m pytest app/back/tests/indexing/node_parsers/test_parent_child_relationships.py app/back/tests/indexing/infrastructure/test_document_factory.py app/back/tests/indexing/infrastructure/test_ingestion_pipeline.py -q --basetemp <workspace-temp>`
  - Result: `10 passed` in the focused indexing-only run and `11 passed` when combined with `test_local_chunking_engine.py`

- Local engine integration:
  - `c:\venvs\chatbot-sst\Scripts\python.exe -m pytest app/back/tests/chunking/integration/test_local_chunking_engine.py -q --basetemp <workspace-temp>`
  - Result: `1 passed`

- Orchestrator integration:
  - `pytest` continues to hit the known Windows cleanup `PermissionError` during session finish in this workspace.
  - Logic was re-verified by direct invocation of:
    - `test_segunda_corrida_reutiliza_artefactos_cuando_fingerprint_no_cambia`
    - `test_cambio_de_overlap_invalida_reutilizacion`
    - `test_fallo_no_deja_bundle_parcial_promovido`
  - Result: `orch-a ok`, `orch-b ok`, `orch-c ok`

## Environment notes

- Revalidation was repeated in the user-provided environment `c:\venvs\chatbot-sst`.
- `c:\venvs\chatbot-sst\Scripts\python.exe -m pip check` returns `No broken requirements found.`
