# ADR-002: Pydantic and LlamaIndex Pins

Date: 2026-07-21

## Status

Accepted for the `llamaparse_experiment` branch.

## Context

The written plan requires granular LlamaIndex packages, not the global
`llama-index` metapackage. The current candidate versions are:

- `llama-cloud==2.12.0`
- `llama-index-core==0.14.23`
- `llama-index-vector-stores-postgres==0.8.1`

The existing project pin `pydantic>=2.0,<2.11` conflicts with current
LlamaIndex because `llama-index-core==0.14.23` depends on
`llama-index-workflows`, which requires `pydantic>=2.11.5`.

## Decision

For this experimental branch:

- Relax the project dependency to `pydantic>=2.11.5,<3`.
- Pin `llama-cloud==2.12.0`.
- Pin `llama-index-core==0.14.23`.
- Pin `llama-index-vector-stores-postgres==0.8.1`.
- Continue rejecting the global `llama-index` metapackage in dependency checks.

## Alternatives Considered

1. Keep `pydantic>=2.0,<2.11` and postpone LlamaIndex work.
2. Search for older LlamaIndex and Postgres integration pairs.
3. Upgrade Pydantic and verify the existing ingestion suite.

Alternative 3 was selected because it unblocks Fase 6 with the current official
packages and the ingestion regression passed after the upgrade.

## Evidence

- `npm run python -- scripts/experiments/check_llama_dependencies.py`
  reported `ok=True` with `pydantic 2.13.4`, `llama-cloud 2.12.0`,
  `llama-index-core 0.14.23`, and
  `llama-index-vector-stores-postgres 0.8.1`.
- `npm run test:ingestion` passed with `276 passed, 3 skipped`.

## Consequences

The branch can implement LlamaIndex indexing against current packages. Any
deployment target using a narrower Pydantic policy must either accept this
upgrade, pin a separately validated older LlamaIndex pair, or disable Fase 6.
