# Operational Documentation Refresh Design

- **Date**: 2026-08-10
- **Scope**: Backend documentation, operational documentation, local planning hygiene
- **Status**: approved for planning and execution

## Goal

Refresh the repository documentation so it reflects the current implemented
state of the `main` branch, documents the full operational flow across backend
areas, and separates active operational guidance from historical or obsolete
planning artifacts.

## Constraints

- The current source of truth is the committed code on the current branch only.
- Uncommitted local changes are treated as work in progress and must not drive
  structural documentation updates.
- Global rules and policies are not rewritten unless the branch proves they are
  inaccurate.
- Files are never deleted without explicit user approval.
- All operational area documents must include the same 12 mandatory sections.
- Documentation must describe both the current implemented state and the
  verified gaps to the target operating model.
- English and Spanish documentation may be normalized for tone and structure if
  that improves clarity and consistency.

## Problem Statement

The repository already contains useful documentation for ingestion, chunking,
Llama-first, observability, rules, ADRs, and some operational instructions, but
it is unevenly distributed across areas:

- some areas have strong README coverage and linked annexes;
- some areas rely mostly on code and scattered handoff documents;
- some operational folders (`memory`, `plans`, `.claude`, `.superpowers`) mix
  durable guidance with historical or session-specific artifacts;
- the current documentation does not provide one canonical backend map that
  explains how data moves from `docs_raw` to retrieval-ready evidence;
- visible technical debt and inconsistencies are not consolidated in one place.

## Design Decision

Adopt a canonical two-level documentation model:

1. **Cross-cutting backend documentation**
   documents the full architecture, phase handoffs, critical variables, and
   known gaps/debt across the operational stack.

2. **Per-area operational READMEs**
   document each implemented area with a uniform mandatory template so the repo
   can be audited consistently.

## Canonical Documentation Structure

### Cross-cutting backend layer

- `docs/backend/README.md`
- `docs/backend/phase-handoffs.md`
- `docs/backend/critical-variables.md`
- `docs/backend/gaps-and-debt.md`

### Area READMEs

- `docs/ingestion/README.md`
- `docs/chunking/README.md`
- `docs/embedding/README.md`
- `docs/indexing/README.md`
- `docs/retrieval/README.md`
- `docs/observability/README.md`
- `docs/llama_first/README.md`

### Supporting navigation

- `docs/README.md`
- root `README.md`
- root `CLAUDE.md`
- local operational guides under `memory/`, `plans/`, `.claude/`, and
  `.superpowers/`

## Mandatory Section Template

Every operational area document must include these 12 sections in order:

1. Purpose and scope
2. Current branch state
3. Code map
4. Inputs and outputs
5. Operational flow
6. Rules and invariants
7. Critical variables and configuration
8. Logs, manifests, and observability
9. Commands and verification
10. Visible inconsistencies and debt
11. Missing pieces to reach the target model
12. References

Area-specific sections may be added, but none of these 12 may be omitted.

## Execution Model

The work is split into two subprojects.

### Subproject A: Versioned technical documentation

Produce or update the canonical documentation for:

- backend-wide architecture and phase handoffs;
- ingestion, chunking, embedding, indexing, retrieval, observability, and
  Llama-first;
- cross-area variables, logs, handoffs, and visible debt.

### Subproject B: Operational hygiene for local guidance

Audit and update:

- `memory/`
- `plans/`
- `.claude/`
- `.superpowers/`
- other local planning guidance files that act as operator instructions

Outputs:

- clearer separation between active guidance, historical plans, and local-only
  artifacts;
- candidate deletion/archive list for explicit user approval;
- no actual deletion until approved.

## Expected Findings to Document

The refreshed docs must explicitly identify:

- phase transitions from raw to normalized, chunked, embedded, indexed, and
  retrievable data;
- key IDs, manifests, and traceability anchors;
- log families and correlation IDs;
- critical environment variables and feature flags;
- structural concentration points, especially large orchestration files;
- visible duplication or spaghetti risks where code paths overlap or contracts
  are scattered;
- differences between current implementation and target operational behavior.

## Validation Strategy

Documentation claims must be checked against:

- committed code under `app/back/src`, `app/front/src`, and `scripts/`;
- package/runtime configuration in `package.json`, `pyproject.toml`,
  `requirements*.txt`, and relevant settings modules;
- tests that prove or constrain current behavior;
- existing versioned docs when they still match the branch.

The work does not invent functionality. When a target behavior is absent, the
docs must mark it as missing or partial rather than describe it as current.

## Risks

- uncommitted local changes may suggest a future state that is not yet the
  branch truth;
- historical planning notes may look authoritative even when the code moved on;
- documentation can drift if cross-area claims are centralized without clear
  source references;
- deleting outdated files without approval would violate the operating
  constraints.

## Mitigations

- derive branch-state claims from committed files only;
- label historical notes and implemented plans explicitly;
- keep references close to the code and docs they summarize;
- generate deletion candidates as recommendations, not direct removals.

## Deliverables

- canonical backend documentation under `docs/backend/`
- refreshed area READMEs with the 12 required sections
- updated navigation docs
- updated local operational guidance
- explicit deletion/archive candidate list pending approval

## Success Criteria

The initiative is complete when:

- every operational area has a canonical README with the 12 mandatory sections;
- the end-to-end backend handoff between phases is documented;
- current-state behavior and target gaps are clearly separated;
- local planning/operational folders are classified and cleaned up
  documentation-wise;
- no file is deleted without explicit approval;
- the documentation can guide a maintainer through how the repo actually works
  today.
