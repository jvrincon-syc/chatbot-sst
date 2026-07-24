# Task 4 Report: Semantic Parent Builder

## Status

Completed without a commit.

## Delivered

- Added `ParentChunkBuilder` to group `StructuralBlock` sequences into
  deterministic semantic parents.
- Sections split on semantic headings instead of page changes.
- Long sections split only at block boundaries.
- Tables and forms remain atomic semantic parents.
- Parent spans merge page and character provenance without introducing overlap.

## Verification

```powershell
$base = Join-Path (Resolve-Path 'pytest-temp').Path ('task4-parents-' + [guid]::NewGuid().ToString('N'))
.\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_parent_chunk_builder.py -q --basetemp $base
```

Result: `5 passed, 1 warning`.

## Files Changed

- `app/back/src/chunking/application/parent_chunk_builder.py`
- `app/back/tests/chunking/unit/test_parent_chunk_builder.py`
