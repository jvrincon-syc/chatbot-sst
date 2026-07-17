# Pipeline Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining Phase 1 ingestion gaps against the historical `memory/fase1.md` contract and the approved schema 2.0 quality design, ending with a portable, fail-closed pipeline and an evidence-backed corpus closure report.

**Architecture:** Preserve the existing schema 2.0 models and capability-specific readers. Restore a green cross-platform baseline first, then make the pipeline compose complete typed bundles, derive document status from material review invariants, and validate the nine audited PDFs semantically before any promotion. Existing normalized output remains untouched until candidate-tree structural and golden gates pass.

**Tech Stack:** Python 3.12, Pydantic 2.10, pytest 8.4, pdfplumber, pypdf, pypdfium2, Pillow, pytesseract, NumPy and OpenCV headless.

## Global Constraints

- `memory/fase1.md` is the Phase 1 scope authority; `memory/plan_trabajo.md` supplies ordering and later-phase boundaries.
- Scope is ingestion and normalization only: no PostgreSQL persistence, chunking, embeddings, RAG, Redis or frontend.
- Canonical paths are raw-root-relative POSIX paths; absolute paths are runtime configuration or explicit legacy fields only.
- Writers emit schema `2.0`; legacy `1.0` is accepted only through the explicit adapter.
- Unknown capability is `not_evaluated`, never `not_detected`.
- A document is `processed` only when coverage, artifacts, measurements and conflicts satisfy the schema 2.0 invariants.
- Candidate output must not mutate `data/docs_normalized` until structural and golden validation both pass.
- Commands use `.venv_windows_trabajo\Scripts\python.exe`; Node.js and the inherited `.venv` are not required.
- Existing user edits are preserved. No commits are created unless the user explicitly asks.

---

### Task 1: Restore a Green, Cross-Platform Baseline

**Files:**
- Modify: `app/back/src/ingestion/classification/rules.py`
- Modify: `app/back/src/ingestion/manifests/bundle_writer.py`
- Test: `app/back/tests/ingestion/test_classification.py`
- Test: `app/back/tests/ingestion/test_bundle_writer.py`
- Test: `app/back/tests/ingestion/test_pipeline_integration.py`

**Interfaces:**
- Preserves: `classify_document(source_relpath, pages, document_control)`.
- Preserves: `write_bundle_atomic(candidate_root, bundle_payload)`.
- Produces: the same atomicity and anti-symlink guarantees on Windows and POSIX.

- [x] **Step 1: Record the current RED baseline**

  Run:

  ```powershell
  .\.venv_windows_trabajo\Scripts\python.exe -m pytest app\back\tests\ingestion\test_classification.py app\back\tests\ingestion\test_bundle_writer.py app\back\tests\ingestion\test_pipeline_integration.py -q
  ```

  Expected: classification fails because `_TOPIC_RULES` is undefined; Windows atomic bundle tests fail because `os.O_DIRECTORY`/`os.O_NOFOLLOW` are unavailable.

- [x] **Step 2: Restore independent type/topic rules**

  Keep `_TYPE_RULES` limited to document types and restore `_TOPIC_RULES` as a separate ordered taxonomy. Preserve title/control > content > filename > route authority and route-only low confidence.

- [x] **Step 3: Verify classification GREEN**

  ```powershell
  .\.venv_windows_trabajo\Scripts\python.exe -m pytest app\back\tests\ingestion\test_classification.py -q
  ```

- [x] **Step 4: Add a platform-neutral secure filesystem backend**

  Keep descriptor-relative `O_NOFOLLOW` operations on platforms that support them. On Windows, use resolved-path containment checks, explicit symlink rejection at every existing parent, same-directory temporary files, `os.replace`, rollback snapshots and cleanup.

- [x] **Step 5: Verify atomic writer and pipeline GREEN**

  ```powershell
  .\.venv_windows_trabajo\Scripts\python.exe -m pytest app\back\tests\ingestion\test_bundle_writer.py app\back\tests\ingestion\test_pipeline_integration.py -q
  ```

---

### Task 2: Compose Complete Canonical Bundles and Fail-Closed Status

**Files:**
- Modify: `app/back/src/ingestion/readers/base.py`
- Modify: `app/back/src/ingestion/pipeline.py`
- Modify: `app/back/src/ingestion/manifests/bundle_writer.py`
- Modify: `app/back/src/ingestion/validation/normalized.py`
- Test: `app/back/tests/ingestion/test_pipeline_integration.py`
- Test: `app/back/tests/ingestion/test_validation.py`

**Interfaces:**
- `ReadResult` carries optional OCR, tables and forms artifacts plus page/document warnings.
- `run_pipeline(...)` writes candidate bundles through `write_bundle_atomic`.
- Document status is calculated once from explicit material review reasons.

- [x] **Step 1: Write failing integration tests**

  Add cases proving that:

  - reader/page warnings propagate to metadata and review manifests;
  - absent table/form capability remains `not_evaluated`;
  - detected table/form observations require their artifacts;
  - OCR/hybrid output requires OCR artifacts;
  - stale optional sidecars are removed when a source no longer produces them;
  - direct writes cannot leave a partial schema 2.0 bundle.

- [x] **Step 2: Verify RED**

  ```powershell
  .\.venv_windows_trabajo\Scripts\python.exe -m pytest app\back\tests\ingestion\test_pipeline_integration.py app\back\tests\ingestion\test_validation.py -q
  ```

- [x] **Step 3: Extend `ReadResult` with forms and capability observations**

  Keep defaults explicit: optional artifact `None` means capability/output is not available, not a negative detection.

- [x] **Step 4: Centralize status derivation**

  Derive material review reasons from incomplete coverage, page warnings, classification/control conflicts, missing required artifacts and invalid metric provenance. Deduplicate reasons deterministically.

- [x] **Step 5: Write complete bundles atomically**

  Build Markdown, metadata, pages, OCR/tables/forms as applicable and pass them to `write_bundle_atomic`. Store bundle hashes in the run manifest and never serialize legacy models as new output.

- [x] **Step 6: Verify GREEN**

  ```powershell
  .\.venv_windows_trabajo\Scripts\python.exe -m pytest app\back\tests\ingestion\test_pipeline_integration.py app\back\tests\ingestion\test_validation.py app\back\tests\ingestion\test_bundle_writer.py -q
  ```

---

### Task 3: Make Golden Validation Semantic and Executable

**Files:**
- Modify: `app/back/src/ingestion/validation/golden.py`
- Modify: `app/back/tests/ingestion/test_golden_validation.py`
- Modify only if required for executable assertions: `docs/ingestion/pdf_corpus_expected.json`

**Interfaces:**
- Preserves: `load_golden(path, raw_root_name="data/docs_raw")`.
- Strengthens: `validate_pdf_corpus(candidate_root, raw_root, golden)`.

- [x] **Step 1: Add failing semantic comparator tests**

  Cover exact document ID/source bijection, metadata type/topic/control/status, page count and contiguity, expected extraction method, observation states, required sidecars, minimum normalized content and localized error details.

- [x] **Step 2: Verify RED**

  ```powershell
  .\.venv_windows_trabajo\Scripts\python.exe -m pytest app\back\tests\ingestion\test_golden_validation.py -q
  ```

- [x] **Step 3: Type the golden expectations**

  Replace unbounded `dict` use for executable fields with strict models while retaining audit prose as non-executable notes.

- [x] **Step 4: Implement semantic comparison**

  Load canonical metadata/pages through schema-aware loaders, compare expected values, require exact nine-PDF bijection and compute actual candidate page totals rather than only summing the golden declaration.

- [x] **Step 5: Verify GREEN**

  ```powershell
  .\.venv_windows_trabajo\Scripts\python.exe -m pytest app\back\tests\ingestion\test_golden_validation.py app\back\tests\ingestion\test_validation.py -q
  ```

---

### Task 4: Candidate Corpus Run and Honest Closure Gate

**Files:**
- Modify: `scripts/ingestion/run_pipeline.py`
- Modify: `scripts/ingestion/validate_normalized.py`
- Create: `app/back/tests/ingestion/test_pdf_corpus_golden.py`
- Modify: `docs/ingestion/phase1_closure_report.md`
- Modify: `docs/ingestion/phase1_checklist.md`

**Interfaces:**
- Candidate pipeline accepts nine explicit PDF source paths.
- Closure validation returns structural and golden reports without promoting on failure.

- [x] **Step 1: Verify capabilities**

  ```powershell
  .\.venv_windows_trabajo\Scripts\python.exe scripts\ingestion\doctor_ocr.py
  ```

  Record Tesseract executable/version/languages, OCRmyPDF, PDFium, pdfplumber and OpenCV independently.

- [x] **Step 2: Add the real-corpus regression**

  Mark it `corpus`; require 9 source PDFs and 77 expected pages. The test must report missing capabilities as an explicit skip/blocker, never as a passing semantic gate.

- [x] **Step 3: Generate an isolated candidate**

  Run only the nine audited PDFs with `force=True`; keep `data/docs_normalized` unchanged.

- [x] **Step 4: Run structural and golden gates**

  No promotion occurs unless both reports pass. Review every remaining `needs_review` reason against the visual audit.

- [x] **Step 5: Run the full verification suite**

  ```powershell
  .\.venv_windows_trabajo\Scripts\python.exe -m pip check
  .\.venv_windows_trabajo\Scripts\python.exe -m pytest app\back\tests\ingestion -q
  .\.venv_windows_trabajo\Scripts\python.exe -m pytest app\back\tests\ingestion\test_pdf_corpus_golden.py -m corpus -q
  ```

- [x] **Step 6: Update closure documentation truthfully**

  Record exact commands, pass/fail counts, capability gaps, document statuses and whether promotion occurred. Do not declare semantic Phase 1 closure while golden failures remain.

---

### Task 5: Connect Implemented Schema 2.0 Capabilities

- [x] Connect table discovery from `pdfplumber` to `TablesArtifact`.
- [x] Connect form evaluation to `FormsArtifact` without treating generic table
  borders as forms.
- [x] Route default digital PDF processing through `HybridReader`.
- [x] Recover split control fields from page-level reading-order evidence.
- [x] Make title/type/topic/subtopic precedence deterministic and evidence-first.
- [x] Execute golden minimum-content requirements by page range.
- [x] Expose closure and golden options in `validate_normalized.py`.

### Task 6: Remaining External and Semantic Blockers

- [ ] Install and verify OCRmyPDF, Tesseract `spa` and Ghostscript.
  OCRmyPDF 16.13.0 and Tesseract 5.4.0 with `spa` are verified;
  Ghostscript 10.07.1 x64 remains an IT dependency.
- [x] Materialize the three scanned bundles and all 77 pages.
- [x] Complete regional OCR for the hybrid pauses-actives document.
- [ ] Add a capable handwriting observation backend.
- [ ] Resolve the current 44 metadata and 69 minimum-content golden
  discrepancies across all nine materialized bundles. Separate genuine
  extraction gaps from descriptive golden prose that is not literal source
  text.
- [ ] Re-run both gates and promote only when both pass.

Current candidate: `.tmp/task6_candidate_full3`.

Current gate state: structural, bijection, page ordering and 77-page total
pass; semantic metadata and content remain failed. Promotion has not occurred.
