# Operational Documentation Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh the repository's operational documentation so it matches the committed state of the current branch, documents all backend operating areas with a mandatory 12-section structure, and separates active local guidance from historical planning artifacts.

**Architecture:** The work is split into two coordinated subprojects. First, create a canonical versioned documentation layer under `docs/` that maps the backend end-to-end and standardizes each operational area. Second, audit the local guidance folders (`memory`, `plans`, `.claude`, `.superpowers`) and update their instructions while producing a deletion candidate list that requires explicit user approval before any removal.

**Tech Stack:** Markdown, git history inspection, PowerShell, ripgrep, Python/Node project metadata, Codex subagents

## Global Constraints

- Use only committed code on the current branch as the source of truth for "current state".
- Treat all uncommitted changes as work in progress and do not use them to rewrite canonical docs.
- Do not delete any file without explicit user approval.
- Do not rewrite global repo rules or policies unless the current branch proves they are inaccurate.
- Every operational area document must include these 12 sections: Purpose and scope; Current branch state; Code map; Inputs and outputs; Operational flow; Rules and invariants; Critical variables and configuration; Logs, manifests, and observability; Commands and verification; Visible inconsistencies and debt; Missing pieces to reach the target model; References.
- Distinguish clearly between implemented current behavior and missing future behavior.
- Keep the write scope inside documentation and local guidance files unless a small supporting doc-only artifact is required.

---

### Task 1: Establish the canonical backend documentation skeleton

**Files:**
- Create: `docs/backend/README.md`
- Create: `docs/backend/phase-handoffs.md`
- Create: `docs/backend/critical-variables.md`
- Create: `docs/backend/gaps-and-debt.md`
- Modify: `docs/README.md`
- Test: documentation self-check against `app/back/src`, `scripts/`, `package.json`, and `pyproject.toml`

**Interfaces:**
- Consumes: approved design in `docs/superpowers/specs/2026-08-10-operational-documentation-refresh-design.md`
- Produces: canonical backend doc layer that later tasks reference from area READMEs

- [ ] **Step 1: Write the failing checklist of missing backend-wide docs**

```markdown
- `docs/backend/README.md` does not exist.
- `docs/backend/phase-handoffs.md` does not exist.
- `docs/backend/critical-variables.md` does not exist.
- `docs/backend/gaps-and-debt.md` does not exist.
- `docs/README.md` does not link a canonical backend layer.
```

- [ ] **Step 2: Run the baseline check to confirm the missing docs**

Run: `rg --files docs backend 2>$null`
Expected: `docs/backend/` files are absent before implementation.

- [ ] **Step 3: Write the minimal canonical backend layer**

```markdown
# Backend Operations

## 1. Purpose and scope
## 2. Current branch state
...
## 12. References
```

Create the four backend docs and update `docs/README.md` so they become the
first path to understand the operational stack.

- [ ] **Step 4: Verify the backend layer against the codebase**

Run: `rg -n "docs_raw|docs_normalized|embedding|indexing|retrieval|feature_flags|configure_structured_logging" app/back/src scripts docs/backend docs/README.md`
Expected: every new backend doc references only code and paths that exist on the current branch.

- [ ] **Step 5: Capture the review-ready diff**

```bash
git diff -- docs/backend/README.md docs/backend/phase-handoffs.md docs/backend/critical-variables.md docs/backend/gaps-and-debt.md docs/README.md
```

### Task 2: Refresh ingestion, chunking, and Llama-first operational documentation

**Files:**
- Modify: `docs/ingestion/README.md`
- Modify: `docs/chunking/README.md`
- Modify: `docs/llama_first/README.md`
- Test: consistency checks against `app/back/src/ingestion/**`, `app/back/src/chunking/**`, `scripts/ingestion/**`, `scripts/chunking/**`

**Interfaces:**
- Consumes: canonical backend docs from Task 1
- Produces: standardized operational READMEs for the raw-to-normalized and chunking layers, plus the experimental overlay

- [ ] **Step 1: Write the failing checklist for section coverage**

```markdown
- `docs/ingestion/README.md` lacks the full 12-section canonical structure.
- `docs/chunking/README.md` does not exist as a canonical README.
- `docs/llama_first/README.md` needs explicit separation between current branch state and target gaps.
```

- [ ] **Step 2: Confirm the current state of those docs**

Run: `rg -n "^## " docs/ingestion/README.md docs/chunking/*.md docs/llama_first/README.md`
Expected: section structure differs from the required 12-section template.

- [ ] **Step 3: Rewrite the area docs to the canonical template**

```markdown
## 1. Purpose and scope
## 2. Current branch state
## 3. Code map
...
## 12. References
```

Preserve useful existing content from ingestion, chunking contracts, and
Llama-first notes, but reorganize it around the mandatory section order.

- [ ] **Step 4: Verify claims and cross-links**

Run: `rg -n "pipeline.py|run_service.py|llama_orchestrator|docs_normalized|Idempotency-Key|LLAMA_" docs/ingestion/README.md docs/chunking/README.md docs/llama_first/README.md app/back/src/ingestion app/back/src/chunking app/back/src/ingestion/application/scripts`
Expected: every path, variable, and runtime statement in the refreshed docs maps to committed files or config.

- [ ] **Step 5: Capture the review-ready diff**

```bash
git diff -- docs/ingestion/README.md docs/chunking/README.md docs/llama_first/README.md
```

### Task 3: Create canonical embedding, indexing, retrieval, and observability READMEs

**Files:**
- Create: `docs/embedding/README.md`
- Create: `docs/indexing/README.md`
- Create: `docs/retrieval/README.md`
- Create: `docs/observability/README.md`
- Test: consistency checks against `app/back/src/embedding/**`, `app/back/src/indexing/**`, `app/back/src/retrieval/**`, `app/back/src/core/logging/**`, `docs/observability/current-contracts.md`

**Interfaces:**
- Consumes: backend layer from Task 1 and existing observability contract docs
- Produces: canonical READMEs for the areas that currently rely mostly on code and scattered handoff docs

- [ ] **Step 1: Write the failing checklist of missing area READMEs**

```markdown
- `docs/embedding/README.md` does not exist.
- `docs/indexing/README.md` does not exist.
- `docs/retrieval/README.md` does not exist.
- `docs/observability/README.md` does not exist as an index README.
```

- [ ] **Step 2: Confirm the missing files**

Run: `Get-ChildItem docs`
Expected: `embedding/`, `indexing/`, and `retrieval/` directories are absent or missing README files before implementation.

- [ ] **Step 3: Write the four READMEs using the 12 required sections**

```markdown
## 1. Purpose and scope
## 2. Current branch state
## 3. Code map
...
## 12. References
```

Ground the content in the committed backend code, the existing API handoff
docs, and the observability contract snapshot.

- [ ] **Step 4: Verify variables, commands, and log claims**

Run: `rg -n "EMBEDDING_|indexing_|retrieval|configure_structured_logging|event" docs/embedding/README.md docs/indexing/README.md docs/retrieval/README.md docs/observability/README.md app/back/src/embedding app/back/src/indexing app/back/src/retrieval app/back/src/core/logging package.json`
Expected: all new docs reference only committed commands, runtime flags, and event families.

- [ ] **Step 5: Capture the review-ready diff**

```bash
git diff -- docs/embedding/README.md docs/indexing/README.md docs/retrieval/README.md docs/observability/README.md
```

### Task 4: Refresh root operational guidance and local guidance contracts

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `memory/README.md`
- Modify: `memory/MEMORY.md`
- Modify: `plans/README.md`
- Modify: `.claude/README.md`
- Modify: `.claude/commands/memoria.md`
- Modify: `.claude/commands/plan.md`
- Modify: `.claude/commands/revisar.md`
- Modify: `.claude/commands/verificar.md`
- Test: consistency checks against repo structure, package scripts, and local-folder purpose

**Interfaces:**
- Consumes: canonical docs from Tasks 1-3
- Produces: synchronized operator guidance between versioned docs and local planning/command folders

- [ ] **Step 1: Write the failing checklist for outdated guidance**

```markdown
- root navigation docs still mix canonical guidance with historical context.
- local guidance folders need clearer separation between active use, history, and non-authoritative notes.
- `.claude` commands and local READMEs need to point at the new canonical documentation layout.
```

- [ ] **Step 2: Confirm the current local guidance map**

Run: `rg --files README.md CLAUDE.md memory plans .claude`
Expected: current local guidance files exist and can be aligned to the new doc structure.

- [ ] **Step 3: Update the local guidance docs**

```markdown
## Canonical source
- versioned operations live under `docs/`
- local planning lives under `plans/`
- historical notes live under `memory/`
```

Update the root and local guidance files so they reference the new canonical
backend docs and make local-folder authority boundaries explicit.

- [ ] **Step 4: Verify command and path references**

Run: `rg -n "docs/backend|docs/ingestion|docs/chunking|docs/embedding|docs/indexing|docs/retrieval|docs/observability|docs/llama_first|npm run" README.md CLAUDE.md memory/README.md memory/MEMORY.md plans/README.md .claude/README.md .claude/commands/*.md`
Expected: the updated guidance points to real docs and real scripts only.

- [ ] **Step 5: Capture the review-ready diff**

```bash
git diff -- README.md CLAUDE.md memory/README.md memory/MEMORY.md plans/README.md .claude/README.md .claude/commands/memoria.md .claude/commands/plan.md .claude/commands/revisar.md .claude/commands/verificar.md
```

### Task 5: Audit plans and historical artifacts, then prepare deletion candidates

**Files:**
- Modify: `memory/MEMORY.md`
- Modify: `plans/README.md`
- Create: `docs/backend/cleanup-candidates.md`
- Test: current-branch implementation checks against `memory/*.md`, `plans/*.md`, `.superpowers/sdd/**`, and existing docs

**Interfaces:**
- Consumes: completed canonical docs and current branch code
- Produces: explicit classification of active/historical/implemented/obsolete artifacts plus a user-approval deletion candidate list

- [ ] **Step 1: Write the failing checklist for cleanup classification**

```markdown
- implemented plans are not clearly distinguished from active plans.
- historical planning notes are not cross-referenced against the current branch state.
- deletion/archive candidates are not listed in one approval-ready document.
```

- [ ] **Step 2: Inspect current local planning artifacts**

Run: `Get-ChildItem memory, plans, .superpowers -Recurse -File`
Expected: identify active plans, historical notes, and stale execution artifacts without deleting anything.

- [ ] **Step 3: Create the cleanup classification document**

```markdown
| Path | Type | Current status | Branch evidence | Recommended action | Requires approval |
| --- | --- | --- | --- | --- | --- |
```

Use current branch code and docs only to decide whether an artifact is active,
historical-but-useful, implemented-and-absorbed, or obsolete.

- [ ] **Step 4: Verify no destructive action occurred**

Run: `git status --short`
Expected: only documentation edits are present; no files were deleted as part of the audit.

- [ ] **Step 5: Capture the review-ready diff**

```bash
git diff -- memory/MEMORY.md plans/README.md docs/backend/cleanup-candidates.md
```

### Task 6: Final verification and review handoff

**Files:**
- Modify: files touched by Tasks 1-5 as needed after review
- Test: repo-wide documentation consistency checks and targeted project verification commands

**Interfaces:**
- Consumes: all prior tasks
- Produces: final consistent documentation set, residual risk notes, and user-facing approval queue for deletions

- [ ] **Step 1: Run documentation consistency checks**

Run: `rg -n "\bTODO\b|\bTBD\b|\bNotImplemented\b|llama_cloud_live|npm --prefix app/front run lint" README.md docs/README.md docs/backend/README.md docs/backend/phase-handoffs.md docs/backend/critical-variables.md docs/backend/gaps-and-debt.md docs/chunking/README.md docs/embedding/README.md docs/indexing/README.md docs/ingestion/README.md docs/llama_first/README.md docs/observability/README.md docs/retrieval/README.md memory/README.md memory/MEMORY.md plans/README.md .claude/README.md .claude/commands/memoria.md .claude/commands/plan.md .claude/commands/revisar.md .claude/commands/verificar.md`
Expected: no newly introduced placeholders or references to non-existent verification gates in the refreshed docs.

- [ ] **Step 2: Run focused project verification commands**

Run: `npm run test:ingestion`
Expected: PASS or existing branch failure reported faithfully.

Run: `npm run test:indexing`
Expected: PASS or existing branch failure reported faithfully.

Run: `npm run test:retrieval`
Expected: PASS or existing branch failure reported faithfully.

- [ ] **Step 3: Request final review**

```text
Description: Refresh operational documentation across backend areas and local guidance, plus prepare cleanup candidates without deleting files.
Requirements: `docs/superpowers/specs/2026-08-10-operational-documentation-refresh-design.md` and `docs/superpowers/plans/2026-08-10-operational-documentation-refresh.md`.
Base SHA command: `git merge-base main HEAD`
Head SHA command: `git rev-parse HEAD`
```

- [ ] **Step 4: Apply review fixes if needed and re-run the affected checks**

Run: `git diff --stat`
Expected: only approved documentation and guidance changes remain.

- [ ] **Step 5: Capture the final review-ready diff**

```bash
git diff -- docs README.md CLAUDE.md memory plans .claude
```
