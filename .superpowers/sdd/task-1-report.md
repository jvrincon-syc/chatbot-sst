# Task 1 Report: Chunking Contracts, Profile, and Invariants

## Status

Completed without a commit. The task creates the chunking domain and
application contracts only; it does not change the active page-based parser or
add a tokenizer, filesystem, FastAPI, SDK, or provider integration.

## Delivered Contract

- Added immutable domain models for `NormalizedDocumentBundle`,
  `StructuralBlock`, `SourceSpan`, `ParentChunk`, `ChildChunk`, `ChunkBundle`,
  `ChunkingProfile`, and `ChunkingRun`.
- Added `local-structural-v1` with child sizes `250/350/450`, overlap ratio
  `0.12`, and overlap bounds `30/60`.
- Enforced profile coherence, non-empty content, valid source spans, existing
  child parents, profile-scoped overlap bounds, and the inclusive child token
  maximum.
- Zero overlap is fail-closed: `local-structural-v1` permits only
  `document_start` and `table_or_form_boundary`. `section_boundary` is defined
  for future profiles but is rejected by this profile.
- IDs, profile fingerprints, bundle fingerprints, and run IDs are SHA-256,
  deterministic, and bound to content, profile, and structural position.
- Added small `TokenCounterPort`, `StructuralChunkerPort`, and
  `ChunkBundleRepositoryPort` protocols with no infrastructure dependency.
- Documented the profile, invariants, zero-overlap policy, and boundaries.

## TDD Evidence

The test module was written before production code. The initial focused run
failed during collection with `ModuleNotFoundError: chunking.domain`, as
expected. Later RED cycles verified that direct construction could bypass
empty-content and deterministic-ID checks; the domain models were then updated
to enforce those invariants during construction.

## Verification

Focused command executed:

```powershell
$env:TMP=(Resolve-Path '.').Path + '\pytest-temp'; $env:TEMP=$env:TMP; New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null; .\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_domain_models.py -q --basetemp .\pytest-basetemp-task1
```

Result: `12 passed` in `0.03s`.

Additional checks:

- `python -m compileall -q app/back/src/chunking` passed.
- `git diff --check` produced no whitespace errors for this task's files.
- A targeted import scan found no Pydantic, FastAPI, filesystem, SDK, parser,
  tokenizer, or network dependency in the new chunking package.

## Concern

Pytest emitted one existing environmental warning because it cannot write to
the repository `.pytest_cache` (`WinError 5`). This did not affect collection
or execution: the focused suite passed using the requested workspace-local
temporary directory and base temp path.

## Review Fixes

Applied the Task 1 review findings without parser or integration changes.

- Bundle fingerprints now include complete canonical parent and child payloads.
  Child payloads include `token_count`, `overlap_tokens`, and
  `zero_overlap_reason`; run IDs also include the complete bundle payload.
- `ChunkBundle.validate_against_document()` validates every parent `block_id`
  against `NormalizedDocumentBundle.blocks`, and `ChunkingRun.create()` invokes
  it before creating run metadata.
- Structural block kinds, profile and policy zero-overlap reason sets, and
  bundle child zero-overlap reasons now receive explicit runtime enum checks.
- Added regression coverage for overlap-only fingerprint changes, unknown
  parent block IDs, and invalid enum values.

Focused review-fix verification executed:

```powershell
$env:TMP=(Resolve-Path '.').Path + '\pytest-temp'; $env:TEMP=$env:TMP; New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null; .\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_domain_models.py -q --basetemp .\pytest-basetemp-task1-fix
```

Result: `16 passed` in `0.07s`. The same existing `.pytest_cache` permission
warning was emitted and did not affect the focused suite.

## Final Review Fix

`ChildChunk` now rejects every non-`None` `zero_overlap_reason` that is not a
`ZeroOverlapReason` during both `ChildChunk.create()` and direct construction
in `__post_init__`. The regression test exercises the factory and direct
dataclass reconstruction path.

Focused final-fix verification executed:

```powershell
$env:TMP=(Resolve-Path '.').Path + '\pytest-temp'; $env:TEMP=$env:TMP; New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null; .\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_domain_models.py -q --basetemp .\pytest-basetemp-task1-fix2
```

Result: `16 passed` in `0.03s`. The existing `.pytest_cache` permission
warning was emitted and did not affect test execution.
