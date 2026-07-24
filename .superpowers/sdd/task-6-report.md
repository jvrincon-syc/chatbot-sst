# Task 6 Report: Local Engine, Persistence, and Active Indexing Adapter

## Status

Completed without a commit.

## Delivered

- Added `LocalChunkingEngine` as the single local implementation of the active
  structural chunking flow: structural parser -> semantic parents ->
  selective children -> validated `ChunkBundle`.
- Refactored the active `StructureAwareNodeParser` so it no longer creates
  parents by page. It now consumes a normalized chunking bundle and delegates
  the actual chunk creation to `LocalChunkingEngine`.
- Kept the indexing contract compatible:
  - parent and child `TextNode` objects are still produced for the docstore
    and vector store;
  - child nodes keep `parent_node_id`, `chunk_index`, char spans, and added
    overlap metadata;
  - table header repetition is injected into the indexed child text through
    `context_prefix`.
- Extended `NormalizedDocumentFactory` and `FilesystemBundleLoader` so the
  indexing path carries the normalized bundle context, including optional
  tables, forms, and OCR sidecars when present.
- Added `Schema2BundleAssembler` to reuse the same normalized-bundle assembly
  logic from both direct chunking and indexing, instead of maintaining a
  divergent second path.
- Added fail-closed filesystem persistence:
  - `FilesystemChunkBundleRepository`
  - `FilesystemRunRepository`
  - `ChunkingOrchestrator`
- Added idempotent reuse by persisted bundle/profile fingerprints and
  fail-closed promotion that only considers a bundle valid when its metadata
  artifact is promoted last.
- Added `scripts/chunking/run_chunking.py` as the local execution entry point.

## Verification

Active indexing adapter regression:

```powershell
$base = Join-Path (Resolve-Path 'pytest-temp').Path ('task6-green-indexing-' + [guid]::NewGuid().ToString('N'))
.\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/indexing/node_parsers/test_parent_child_relationships.py app/back/tests/indexing/infrastructure/test_document_factory.py app/back/tests/indexing/infrastructure/test_ingestion_pipeline.py -q --basetemp $base
```

Result: `10 passed, 1 warning`.

Local engine integration:

```powershell
$base = Join-Path (Resolve-Path 'pytest-temp').Path ('task6-red-engine-' + [guid]::NewGuid().ToString('N'))
.\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/integration/test_local_chunking_engine.py -q --basetemp $base
```

Result: `1 passed, 1 warning`.

Manual orchestrator harness:

```powershell
.\.venv_windows_trabajo\Scripts\python.exe -c "<invoke test_segunda_corrida_reutiliza_artefactos_cuando_fingerprint_no_cambia>"
.\.venv_windows_trabajo\Scripts\python.exe -c "<invoke test_cambio_de_overlap_invalida_reutilizacion>"
.\.venv_windows_trabajo\Scripts\python.exe -c "<invoke test_fallo_no_deja_bundle_parcial_promovido>"
```

Result: all three scenarios passed (`task6-a ok`, `task6-b ok`, `task6-c ok`).

Static verification:

```powershell
.\.venv_windows_trabajo\Scripts\python.exe -m compileall -q app/back/src/chunking app/back/src/indexing/infrastructure/llama_index
```

Result: passed.

## Files Changed

- `app/back/src/chunking/application/local_chunking_engine.py`
- `app/back/src/chunking/application/chunking_orchestrator.py`
- `app/back/src/chunking/application/ports.py`
- `app/back/src/chunking/infrastructure/schema2_source.py`
- `app/back/src/chunking/infrastructure/filesystem_chunk_repository.py`
- `app/back/src/chunking/infrastructure/filesystem_run_repository.py`
- `app/back/src/indexing/infrastructure/llama_index/document_factory.py`
- `app/back/src/indexing/infrastructure/llama_index/node_parsers/structure_aware.py`
- `app/back/src/indexing/infrastructure/llama_index/pipeline_factory.py`
- `app/back/tests/chunking/integration/test_local_chunking_engine.py`
- `app/back/tests/chunking/integration/test_chunking_orchestrator.py`
- `app/back/tests/indexing/node_parsers/test_parent_child_relationships.py`
- `scripts/chunking/run_chunking.py`

## Notes

- The Windows workspace still triggers an environmental `pytest` cleanup
  failure around `tmp_path`/`basetemp` listing for some integration tests. The
  new orchestrator scenarios were therefore verified through direct Python
  harness execution against workspace-local temp directories, which passed.
- The active path no longer depends on `page_catalog` for chunk generation.
  `page_catalog` remains in document metadata only as a compatibility artifact.
