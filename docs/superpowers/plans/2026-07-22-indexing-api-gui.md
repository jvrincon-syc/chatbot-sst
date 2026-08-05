# Indexing API And GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an administrative GUI and API surface that lets operators select eligible documents, preview LlamaIndex chunks, choose one embedding profile at a time, create embeddings, and persist them through the backend into the configured store.

**Architecture:** Add a thin indexing API over the existing Llama-first indexing services, then add a dedicated frontend view inside the current operations UI. The API must return jobs and status instead of hiding long-running work inside a blocking request. The GUI is administrative: it shows eligibility, ingestion origin, selected embedding profile, chunk preview, run status, validation, and blockers without exposing secrets or raw provider payloads.

**Tech Stack:** Current GUI API server in `app/back/src/ingestion/gui/server.py`, indexing application services, React + TypeScript frontend, lucide-react icons, pytest, frontend unit tests, Vite build.

## Global Constraints

- This plan assumes `docs/superpowers/plans/2026-07-22-postgres-pgvector-indexing.md` has produced the profile/orchestrator contracts.
- This plan targets the Llama-first branch, not `main`.
- `memory/plan_trabajo.md` is the general product vision; this branch prioritizes Llama-first and LlamaIndex.
- The GUI must operate only over `processed` or explicitly approved documents.
- The GUI must never silently include `needs_review`.
- The GUI must keep local-ingested normalized bundles and Llama-ingested normalized bundles in separate lanes.
- The GUI must let the operator switch between BGE, Voyage, Cohere, and mock/test profiles, but only one selected profile can be used per indexing run.
- The GUI must not merge embeddings across providers, models, dimensions, chunking versions, corpus versions, or ingestion origins.
- PostgreSQL persistence controls remain blocked until infrastructure is confirmed.
- API responses must not include secrets, API keys, signed URLs, stack traces, prompts, full provider payloads, or complete corporate document bodies.
- Use typed frontend services; do not scatter `fetch` calls in components.
- Keep frontend state explicit: idle, loading, success, empty, error, blocked, cancelled.
- Do not add a marketing page; this is an operational admin screen.

## Current Evidence

- `app/back/src/ingestion/gui/server.py` already exposes `/api/status`, `/api/pipeline/run`, `/api/validate`, `/api/promote`, upload, settings, and review endpoints.
- `app/front/src/App.tsx` already has views for operations, review, and inventory.
- `app/front/src/pipelineRequest.ts` centralizes the ingestion pipeline request shape.
- `scripts/indexing/run_indexing.py` already supports indexing via CLI, but not typed GUI API endpoints or async job status.
- Existing frontend currently calls `fetch` directly from `App.tsx`; this plan moves new indexing calls into `services/indexingApi.ts` without rewriting existing ingestion calls.

## API Surface

Add these endpoints to the current GUI API server first, while keeping the route handlers thin:

```text
GET  /api/indexing/status
GET  /api/indexing/profiles
GET  /api/indexing/documents?origin=llama_cloud&eligibleOnly=true
POST /api/indexing/preview
POST /api/indexing/jobs
GET  /api/indexing/jobs/{job_id}
POST /api/indexing/jobs/{job_id}/cancel
POST /api/indexing/validate
```

The endpoints should delegate to indexing application services, not implement business logic in the HTTP handler.

## File Structure

- Create: `app/back/src/indexing/application/eligibility.py`  
  Selects eligible documents and explains exclusions.
- Create: `app/back/src/indexing/application/chunk_preview.py`  
  Produces bounded chunk previews from LlamaIndex parser output.
- Create: `app/back/src/indexing/application/jobs.py`  
  Job models, status transitions, cancellation, and run summaries.
- Create: `app/back/src/indexing/infrastructure/jobs/file_job_store.py`  
  Durable job state under `data/docs_normalized/_manifests/indexing_jobs.json`.
- Create: `app/back/src/indexing/gui/api.py`  
  Pure request/response helpers used by `ingestion.gui.server`.
- Modify: `app/back/src/ingestion/gui/server.py`  
  Add indexing routes and wire helpers.
- Test: `app/back/tests/indexing/application/test_eligibility.py`
- Test: `app/back/tests/indexing/application/test_chunk_preview.py`
- Test: `app/back/tests/indexing/application/test_jobs.py`
- Test: `app/back/tests/indexing/gui/test_indexing_api.py`
- Create: `app/front/src/types/indexing.ts`
- Create: `app/front/src/services/indexingApi.ts`
- Create: `app/front/src/features/indexing/IndexingWorkspace.tsx`
- Create: `app/front/src/features/indexing/EmbeddingProfileSelector.tsx`
- Create: `app/front/src/features/indexing/EligibleDocumentsTable.tsx`
- Create: `app/front/src/features/indexing/ChunkPreviewPanel.tsx`
- Create: `app/front/src/features/indexing/IndexingRunPanel.tsx`
- Create: `app/front/src/features/indexing/PgVectorReadinessPanel.tsx`
- Modify: `app/front/src/App.tsx`
- Modify: `app/front/src/styles.css`
- Create: `app/front/src/features/indexing/indexingState.test.mjs`
- Create: `app/front/src/services/indexingApi.test.mjs`
- Modify: `package.json` only if new scripts are required.
- Create: `docs/runbooks/indexing-gui.md`

---

### Task 1: Backend Eligibility Service

**Files:**
- Create: `app/back/src/indexing/application/eligibility.py`
- Test: `app/back/tests/indexing/application/test_eligibility.py`

**Interfaces:**
- Produces: `IndexingEligibilityService.evaluate(record: dict, decision: ReviewDecision | None) -> EligibilityResult`
- Produces result fields: `document_id`, `source_relpath`, `eligible`, `reason`, `ingestion_origin`, `source_hash`

- [ ] **Step 1: Write failing tests**

```python
from indexing.application.eligibility import IndexingEligibilityService


def test_processed_document_is_eligible() -> None:
    result = IndexingEligibilityService().evaluate(
        record={
            "document_id": "doc_1",
            "source_relpath": "manual/doc.pdf",
            "processing_status": "processed",
            "source_hash": "a" * 64,
            "ingestion_provider": "llama_cloud",
        },
        decision=None,
    )

    assert result.eligible is True
    assert result.reason == "processed"


def test_needs_review_without_approval_is_excluded() -> None:
    result = IndexingEligibilityService().evaluate(
        record={
            "document_id": "doc_2",
            "source_relpath": "manual/review.pdf",
            "processing_status": "needs_review",
            "source_hash": "b" * 64,
            "ingestion_provider": "llama_cloud",
        },
        decision=None,
    )

    assert result.eligible is False
    assert result.reason == "needs_review_without_approval"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run python -- -m pytest app/back/tests/indexing/application/test_eligibility.py -q`  
Expected: FAIL because `eligibility.py` does not exist.

- [ ] **Step 3: Implement minimal service**

```python
from __future__ import annotations

from pydantic import Field

from ingestion.schemas.common import StrictModel


class EligibilityResult(StrictModel):
    document_id: str = Field(min_length=1)
    source_relpath: str = Field(min_length=1)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ingestion_origin: str = Field(pattern=r"^(local|llama_cloud)$")
    eligible: bool
    reason: str = Field(min_length=1)


class IndexingEligibilityService:
    def evaluate(self, *, record: dict, decision: object | None) -> EligibilityResult:
        status = str(record.get("processing_status", ""))
        origin = str(record.get("ingestion_provider") or record.get("ingestionProvider") or "local")
        eligible = status == "processed"
        reason = "processed" if eligible else "needs_review_without_approval"
        if status == "needs_review" and decision is not None:
            decision_value = getattr(decision, "decision", None)
            if decision_value == "approved":
                eligible = True
                reason = "human_approved"
        if status not in {"processed", "needs_review"}:
            eligible = False
            reason = f"unsupported_status:{status or 'missing'}"
        return EligibilityResult(
            document_id=str(record["document_id"]),
            source_relpath=str(record["source_relpath"]),
            source_hash=str(record.get("source_hash") or record.get("content_hash")),
            ingestion_origin=origin,
            eligible=eligible,
            reason=reason,
        )
```

- [ ] **Step 4: Run tests**

Run: `npm run python -- -m pytest app/back/tests/indexing/application/test_eligibility.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/back/src/indexing/application/eligibility.py app/back/tests/indexing/application/test_eligibility.py
git commit -m "feat(indexing): add document eligibility service"
```

---

### Task 2: Bounded Chunk Preview Service

**Files:**
- Create: `app/back/src/indexing/application/chunk_preview.py`
- Test: `app/back/tests/indexing/application/test_chunk_preview.py`

**Interfaces:**
- Produces: `ChunkPreviewService.preview(document: IndexableDocument, limit: int) -> ChunkPreview`
- Consumes existing `FilesystemBundleLoader`, `NormalizedDocumentFactory`, `StructureAwareNodeParser`

- [ ] **Step 1: Write failing tests**

```python
from indexing.application.chunk_preview import ChunkPreviewService


def test_chunk_preview_is_bounded_and_marks_parent_child_roles(static_indexable_document):
    preview = ChunkPreviewService(bundle_loader=StaticBundleLoader()).preview(
        document=static_indexable_document,
        limit=5,
    )

    assert preview.document_id == "doc_1"
    assert preview.total_nodes >= 2
    assert {node.node_role for node in preview.nodes} == {"parent", "child"}
    assert all(len(node.text_sample) <= 240 for node in preview.nodes)
```

- [ ] **Step 2: Run test to verify failure**

Run: `npm run python -- -m pytest app/back/tests/indexing/application/test_chunk_preview.py -q`  
Expected: FAIL because service does not exist.

- [ ] **Step 3: Implement preview**

Rules:
- Do not return complete document text.
- Return at most `limit` nodes.
- Return text samples capped at 240 characters.
- Include `node_id`, `node_role`, `parent_node_id`, `page_start`, `page_end`, `section_title`, `token_count` if available.

- [ ] **Step 4: Run tests**

Run: `npm run python -- -m pytest app/back/tests/indexing/application/test_chunk_preview.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/back/src/indexing/application/chunk_preview.py app/back/tests/indexing/application/test_chunk_preview.py
git commit -m "feat(indexing): add bounded chunk preview service"
```

---

### Task 3: Indexing Job Model And Store

**Files:**
- Create: `app/back/src/indexing/application/jobs.py`
- Create: `app/back/src/indexing/infrastructure/jobs/file_job_store.py`
- Test: `app/back/tests/indexing/application/test_jobs.py`

**Interfaces:**
- Produces: `IndexingJob`
- Produces: `IndexingJobStore.create(request)`, `get(job_id)`, `update(job)`
- States: `pending`, `running`, `completed`, `failed`, `cancelled`, `blocked`

- [ ] **Step 1: Write failing tests**

```python
from indexing.application.jobs import IndexingJobRequest, IndexingJobStore


def test_job_store_creates_pending_job(tmp_path) -> None:
    store = FileIndexingJobStore(tmp_path / "indexing_jobs.json")
    job = store.create(
        IndexingJobRequest(
            profile_id="llama-bge-m3-v1",
            ingestion_origin="llama_cloud",
            document_ids=["doc_1"],
            dry_run=False,
            store="memory",
        )
    )

    assert job.status == "pending"
    assert job.document_ids == ["doc_1"]
```

- [ ] **Step 2: Run test to verify failure**

Run: `npm run python -- -m pytest app/back/tests/indexing/application/test_jobs.py -q`  
Expected: FAIL because job model/store do not exist.

- [ ] **Step 3: Implement file job store**

The file store writes atomically under `_manifests`. It stores IDs, statuses, timestamps, document counts, selected profile, selected ingestion origin, run summary, warnings, and controlled errors.

- [ ] **Step 4: Run tests**

Run: `npm run python -- -m pytest app/back/tests/indexing/application/test_jobs.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/back/src/indexing/application/jobs.py app/back/src/indexing/infrastructure/jobs/file_job_store.py app/back/tests/indexing/application/test_jobs.py
git commit -m "feat(indexing): add indexing job store"
```

---

### Task 4: Indexing API Helpers

**Files:**
- Create: `app/back/src/indexing/gui/api.py`
- Modify: `app/back/src/ingestion/gui/server.py`
- Test: `app/back/tests/indexing/gui/test_indexing_api.py`

**Interfaces:**
- Produces helper functions:
  - `indexing_status_payload() -> dict`
  - `indexing_profiles_payload() -> dict`
  - `indexing_documents_payload(origin: str | None, eligible_only: bool) -> dict`
  - `indexing_preview_payload(body: dict) -> dict`
  - `create_indexing_job_payload(body: dict) -> dict`
  - `indexing_job_payload(job_id: str) -> dict`
  - `cancel_indexing_job_payload(job_id: str) -> dict`
  - `validate_indexing_payload(body: dict) -> dict`

- [ ] **Step 1: Write failing API tests**

```python
from indexing.gui.api import indexing_documents_payload


def test_indexing_documents_payload_excludes_needs_review_by_default(tmp_path):
    payload = indexing_documents_payload(
        records=[
            {"document_id": "doc_1", "source_relpath": "a.pdf", "processing_status": "processed", "source_hash": "a" * 64, "ingestion_provider": "llama_cloud"},
            {"document_id": "doc_2", "source_relpath": "b.pdf", "processing_status": "needs_review", "source_hash": "b" * 64, "ingestion_provider": "llama_cloud"},
        ],
        decisions={},
        origin=None,
        eligible_only=True,
    )

    assert [doc["documentId"] for doc in payload["documents"]] == ["doc_1"]
```

- [ ] **Step 2: Run test to verify failure**

Run: `npm run python -- -m pytest app/back/tests/indexing/gui/test_indexing_api.py -q`  
Expected: FAIL because helpers do not exist.

- [ ] **Step 3: Implement helpers and wire routes**

Add routes to `Phase1GuiHandler.do_GET`:

```python
if path == "/api/indexing/status":
    self._send_json(indexing_status_payload())
    return
if path == "/api/indexing/profiles":
    self._send_json(indexing_profiles_payload())
    return
if path == "/api/indexing/documents":
    query = parse_qs(urlparse(self.path).query)
    self._send_json(indexing_documents_payload_from_query(query))
    return
```

Add routes to `do_POST`:

```python
if path == "/api/indexing/preview":
    self._send_json(indexing_preview_payload(self._read_json_body()))
    return
if path == "/api/indexing/jobs":
    self._send_json(create_indexing_job_payload(self._read_json_body()), status=HTTPStatus.ACCEPTED)
    return
if path.startswith("/api/indexing/jobs/") and path.endswith("/cancel"):
    job_id = unquote(path.removeprefix("/api/indexing/jobs/").removesuffix("/cancel"))
    self._send_json(cancel_indexing_job_payload(job_id))
    return
if path == "/api/indexing/validate":
    self._send_json(validate_indexing_payload(self._read_json_body(required=False)))
    return
```

- [ ] **Step 4: Run API tests**

Run: `npm run python -- -m pytest app/back/tests/indexing/gui/test_indexing_api.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/back/src/indexing/gui/api.py app/back/src/ingestion/gui/server.py app/back/tests/indexing/gui/test_indexing_api.py
git commit -m "feat(indexing): expose administrative indexing api"
```

---

### Task 5: Frontend Types And API Service

**Files:**
- Create: `app/front/src/types/indexing.ts`
- Create: `app/front/src/services/indexingApi.ts`
- Create: `app/front/src/services/indexingApi.test.mjs`

**Interfaces:**
- Produces:
  - `fetchIndexingStatus()`
  - `fetchIndexingProfiles()`
  - `fetchIndexingDocuments(params)`
  - `previewChunks(request)`
  - `createIndexingJob(request)`
  - `fetchIndexingJob(jobId)`
  - `cancelIndexingJob(jobId)`
  - `validateIndexing(request)`

- [ ] **Step 1: Write failing service tests**

```javascript
import assert from "node:assert/strict";
import { requestBodyForIndexingJob } from "../.tmp-tests/indexingApi.js";

const body = requestBodyForIndexingJob({
  profileId: "llama-bge-m3-v1",
  ingestionOrigin: "llama_cloud",
  documentIds: ["doc_1"],
  store: "memory",
  dryRun: false,
});

assert.deepEqual(body, {
  profileId: "llama-bge-m3-v1",
  ingestionOrigin: "llama_cloud",
  documentIds: ["doc_1"],
  store: "memory",
  dryRun: false,
});
```

- [ ] **Step 2: Run frontend test to verify failure**

Run: `npm --prefix app/front run test`  
Expected: FAIL until service helper exists and test compile step includes it.

- [ ] **Step 3: Implement typed service**

All request/response types live in `types/indexing.ts`. The service is the only new frontend module that calls `fetch`.

- [ ] **Step 4: Run frontend tests**

Run: `npm --prefix app/front run test`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/front/src/types/indexing.ts app/front/src/services/indexingApi.ts app/front/src/services/indexingApi.test.mjs
git commit -m "feat(front): add typed indexing api client"
```

---

### Task 6: Indexing Workspace UI

**Files:**
- Create: `app/front/src/features/indexing/IndexingWorkspace.tsx`
- Create: `app/front/src/features/indexing/EmbeddingProfileSelector.tsx`
- Create: `app/front/src/features/indexing/EligibleDocumentsTable.tsx`
- Create: `app/front/src/features/indexing/ChunkPreviewPanel.tsx`
- Create: `app/front/src/features/indexing/IndexingRunPanel.tsx`
- Create: `app/front/src/features/indexing/PgVectorReadinessPanel.tsx`
- Modify: `app/front/src/App.tsx`
- Modify: `app/front/src/styles.css`

**Interfaces:**
- Consumes typed API service from Task 5.
- Produces new app view: `indexing`.

- [ ] **Step 1: Write failing state/helper tests**

```javascript
import assert from "node:assert/strict";
import { canStartIndexingRun } from "../.tmp-tests/indexingState.js";

assert.equal(
  canStartIndexingRun({
    selectedDocumentIds: ["doc_1"],
    selectedProfileId: "llama-bge-m3-v1",
    postgresReady: false,
    store: "postgres",
  }).allowed,
  false,
);
```

- [ ] **Step 2: Run frontend tests to verify failure**

Run: `npm --prefix app/front run test`  
Expected: FAIL because helper/view does not exist.

- [ ] **Step 3: Implement UI**

Add `AppView = "operations" | "review" | "inventory" | "indexing"`.

The workspace includes:
- profile selector with BGE, Voyage, Cohere, mock profiles;
- ingestion origin segmented control: Llama / Local;
- table of eligible documents only by default;
- excluded count with reasons;
- chunk preview button for selected document;
- store selector: memory / postgres;
- blocked state when postgres is selected but not confirmed;
- run button that creates a job;
- job status panel with polling;
- validation button.

Do not show full document bodies. Preview samples stay capped.

- [ ] **Step 4: Run frontend checks**

Run:

```bash
npm --prefix app/front run test
npm --prefix app/front run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/front/src/features/indexing app/front/src/App.tsx app/front/src/styles.css app/front/src/features/indexing/indexingState.test.mjs
git commit -m "feat(front): add indexing operations workspace"
```

---

### Task 7: Backend Job Execution

**Files:**
- Modify: `app/back/src/indexing/application/jobs.py`
- Create: `app/back/src/indexing/application/run_indexing_job.py`
- Modify: `app/back/src/indexing/gui/api.py`
- Test: `app/back/tests/indexing/application/test_jobs.py`
- Test: `app/back/tests/indexing/gui/test_indexing_api.py`

**Interfaces:**
- Produces: `RunIndexingJobUseCase.run(job_id: str) -> IndexingJob`
- API `POST /api/indexing/jobs` returns `202 Accepted` and a `jobId`.

- [ ] **Step 1: Write failing tests**

```python
def test_create_job_returns_blocked_when_postgres_not_confirmed() -> None:
    payload = create_indexing_job_payload(
        {
            "profileId": "llama-bge-m3-v1",
            "ingestionOrigin": "llama_cloud",
            "documentIds": ["doc_1"],
            "store": "postgres",
            "dryRun": False,
        },
        postgres_confirmed=False,
    )

    assert payload["status"] == "blocked"
    assert payload["reason"] == "postgres_not_confirmed"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `npm run python -- -m pytest app/back/tests/indexing/application/test_jobs.py app/back/tests/indexing/gui/test_indexing_api.py -q`  
Expected: FAIL until job execution handles blocked states.

- [ ] **Step 3: Implement job execution**

Rules:
- Synchronous internals may run in a worker thread, but API returns a job immediately.
- Store every transition.
- Cancellation is cooperative and stops before starting the next document.
- Failures are per-job and per-document; do not hide partial results.
- `dryRun=true` never writes vectors.

- [ ] **Step 4: Run backend indexing/API tests**

Run:

```bash
npm run python -- -m pytest app/back/tests/indexing/application app/back/tests/indexing/gui -q
npm run test:indexing
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/back/src/indexing/application app/back/src/indexing/gui/api.py app/back/tests/indexing
git commit -m "feat(indexing): run indexing through tracked jobs"
```

---

### Task 8: End-To-End Admin Flow Verification And Runbook

**Files:**
- Create: `docs/runbooks/indexing-gui.md`
- Modify: `docs/llama_first/README.md`

**Interfaces:**
- Documents local memory flow now.
- Documents PostgreSQL flow as blocked until infrastructure is confirmed.

- [ ] **Step 1: Add runbook content**

The runbook must include:
- prerequisites;
- start commands: `npm run gui:api`, `npm run gui:front`;
- how to select ingestion origin;
- how to select embedding profile;
- how to preview chunks;
- how to run memory/dry-run;
- how to recognize PostgreSQL blocked state;
- how to validate;
- rollback: delete only profile-specific rows using backend command, never manual table truncation without backup;
- security warning: no secrets or full document bodies in screenshots/logs.

- [ ] **Step 2: Run verification commands**

```bash
npm run python -- -m pytest app/back/tests/indexing -q
npm --prefix app/front run test
npm --prefix app/front run build
npm run indexing:run -- --dry-run
npm run indexing:validate
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/indexing-gui.md docs/llama_first/README.md
git commit -m "docs(indexing): document indexing gui operation"
```

## Final Verification

Run:

```bash
npm run python -- -m pip check
npm run test:indexing
npm run indexing:run -- --dry-run
npm run indexing:validate
npm --prefix app/front run test
npm --prefix app/front run lint
npm --prefix app/front run build
```

If `npm --prefix app/front run lint` does not exist, document the equivalent or add the script before claiming completion.

## Definition Of Done

- API exposes typed indexing status, profiles, documents, preview, jobs, cancellation, and validation.
- API excludes unapproved `needs_review` by default.
- API blocks PostgreSQL persistence until infrastructure is confirmed.
- GUI has a dedicated administrative indexing view.
- GUI shows eligible and excluded documents with reasons.
- GUI shows ingestion origin and selected embedding profile clearly.
- GUI allows switching BGE, Voyage, Cohere, and mock profiles without mixing providers.
- GUI shows chunk preview using bounded samples only.
- GUI starts indexing as a tracked job and shows job status.
- GUI distinguishes memory/dry-run from PostgreSQL persistence.
- Frontend API calls are centralized in `services/indexingApi.ts`.
- Loading, empty, success, blocked, cancelled, and error states are visible.
- Backend tests, frontend tests, and frontend build pass.
- Runbook is updated.

