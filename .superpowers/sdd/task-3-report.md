# Task 3 Report: Structural Parser

## Status

Completed without a commit.

## Delivered

- Added `MarkdownAdapter` to extract headings, article/numeral headings, lists,
  tables, and paragraphs from normalized Markdown without turning page markers
  into hard boundaries.
- Added `StructuralParser` to transform a `NormalizedDocumentBundle` into
  ordered `StructuralBlock` instances with deterministic IDs and auditable
  source spans.
- Repeated non-semantic headings are only downgraded to `NOTE` when they are
  repeated and appear near the start of a page, which keeps real repeated
  section headings semantic while still filtering page-header style noise such
  as `SYC`.
- Numbered lists such as `1.` and `2.` are parsed as `LIST`, not as semantic
  headings.
- The parser is fail-closed on page provenance: if a structural region falls
  outside the resolved `page_traces`, parsing raises
  `PAGE_TRACE_UNRESOLVED` instead of silently emitting a block with unknown
  pages.

## Verification

```powershell
$base = Join-Path (Resolve-Path 'pytest-temp').Path ('task3-structural-green2-' + [guid]::NewGuid().ToString('N'))
.\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_structural_parser.py -q --basetemp $base
```

Result: `9 passed, 1 warning`.

Additional regression:

```powershell
$base = Join-Path (Resolve-Path 'pytest-temp').Path ('task3-domain-recheck-' + [guid]::NewGuid().ToString('N'))
.\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_domain_models.py app/back/tests/chunking/unit/test_structural_parser.py app/back/tests/chunking/unit/test_parent_chunk_builder.py -q --basetemp $base
```

Result: `31 passed, 1 warning`.

## Files Changed

- `app/back/src/chunking/infrastructure/markdown_adapter.py`
- `app/back/src/chunking/application/structural_parser.py`
- `app/back/src/chunking/domain/models.py`
- `app/back/tests/chunking/unit/test_structural_parser.py`
- `app/back/tests/chunking/unit/test_domain_models.py`

## Review Fixes

- Numbered-list lines are parsed as list content before article-heading
  heuristics run.
- Repeated-heading filtering now also requires proximity to the start of the
  page trace and a short/mostly-uppercase signal.
- Missing page provenance now aborts parsing instead of leaking blocks with
  `page_start=None` and `page_end=None`.
