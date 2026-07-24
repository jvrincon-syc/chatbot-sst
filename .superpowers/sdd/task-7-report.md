# Task 7 Report

## Scope completed

- Implemented `ChunkingRunService` as the application boundary for local chunking runs.
- Added FastAPI request/response schemas, dependency wiring, router, and app composition under `app/back/src/chunking/api/`.
- Exposed `/api/chunking` endpoints for profiles, runs, run documents, validation, parents, and children.
- Kept business logic out of the routes; routes only validate, dispatch, and translate errors.
- Added structured logging for run creation, submission, start, document completion, run completion, and failure.
- Replaced request-bound execution with a single-worker `ThreadPoolExecutor` and persisted run manifests before scheduling.
- Standardized the error envelope for domain errors, request validation (`422`), and unknown chunking routes.
- Tightened OpenAPI by adding typed response models for success payloads and error responses.
- Made `Idempotency-Key` mandatory and added explicit contract coverage for the missing-header case.

## Tests added or updated

- `app/back/tests/chunking/api/test_chunking_api.py`
  - Added the 9 minimum Task 7 tests.
  - Added explicit `422` coverage for invalid `scope`.
  - Added explicit `422` coverage for missing `Idempotency-Key`.
  - Added uniform-error coverage for unknown chunking routes.
  - Extended OpenAPI assertions to verify additional paths and component schemas.

## Verification

- API contract suite:
  - `c:\venvs\chatbot-sst\Scripts\python.exe -m pytest app/back/tests/chunking/api/test_chunking_api.py -q --basetemp <workspace-temp>`
  - Result: `12 passed`

## Notes

- This branch had no pre-existing backend FastAPI composition point. Task 7 therefore introduced a standalone FastAPI composition module instead of plugging into an existing app.
- Known follow-ups remain documented in `docs/chunking/api_contract.md` and `docs/chunking/decision-log.md`:
  - no restart-time run-state reconstruction;
  - no pagination yet for parents/children;
  - `run_id` on parent listing validates existence but does not select historical run-scoped artifacts.
