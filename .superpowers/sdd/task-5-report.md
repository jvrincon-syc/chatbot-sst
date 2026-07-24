# Task 5 Report: Child Chunk Builder

## Status

Completed without a commit.

## Delivered

- Added `CanonicalTokenizer` backed by `tiktoken` `cl100k_base` as the
  canonical token counter for local chunk sizing.
- Added `ChildChunkBuilder` to generate deterministic children for three
  cases: continuous text, tables, and atomic structural parents.
- Continuous text now:
  - targets the `250/350/450` bounds from `local-structural-v1`;
  - computes semantic overlap with full sentence units only;
  - records bounded `overlap_previous_tokens` and `overlap_next_tokens`;
  - tracks real token offsets against the parent text instead of character
    offsets mislabeled as tokens.
- Table children repeat headers as `context_prefix` and never duplicate rows
  through overlap.
- Forms, self-contained lists, and single-child parents remain zero-overlap.
- `ParentChunkBuilder` now sizes semantic parents with the same canonical
  tokenizer used by child chunking, eliminating the previous word-count drift.

## Verification

Focused child suite:

```powershell
$base = Join-Path (Resolve-Path 'pytest-temp').Path ('task5-green4-' + [guid]::NewGuid().ToString('N'))
.\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_child_chunk_builder.py -q --basetemp $base
```

Result: `12 passed, 1 warning`.

Focused parent suite:

```powershell
$base = Join-Path (Resolve-Path 'pytest-temp').Path ('task5-parent-green2-' + [guid]::NewGuid().ToString('N'))
.\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_parent_chunk_builder.py -q --basetemp $base
```

Result: `6 passed, 1 warning`.

Focused core regression:

```powershell
$base = Join-Path (Resolve-Path 'pytest-temp').Path ('task5-core-green2-' + [guid]::NewGuid().ToString('N'))
.\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_domain_models.py app/back/tests/chunking/unit/test_structural_parser.py app/back/tests/chunking/unit/test_parent_chunk_builder.py app/back/tests/chunking/unit/test_child_chunk_builder.py -q --basetemp $base
```

Result: `45 passed, 1 warning`.

## Files Changed

- `app/back/src/chunking/infrastructure/canonical_tokenizer.py`
- `app/back/src/chunking/application/child_chunk_builder.py`
- `app/back/src/chunking/application/parent_chunk_builder.py`
- `app/back/src/chunking/domain/models.py`
- `app/back/src/chunking/domain/policies.py`
- `app/back/tests/chunking/unit/test_child_chunk_builder.py`
- `app/back/tests/chunking/unit/test_domain_models.py`
- `app/back/tests/chunking/unit/test_parent_chunk_builder.py`

## Notes

- A review subagent could not complete because the environment hit its usage
  limit. I compensated with an additional local invariants pass and new
  regression tests for token-span traceability and canonical parent sizing.
- The existing `.pytest_cache` permission warning remains environmental and did
  not affect focused execution under workspace-local `--basetemp` paths.
