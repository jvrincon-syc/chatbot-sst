# ADR-004: Production Parser Routing

Date: 2026-07-21

## Status

Proposed for the experiment.

## Context

The plan allows either full Llama-first adoption or selective Llama-first
routing. Live cloud smoke tests are blocked until data and budget approvals are
available.

## Decision

Keep routing behind feature flags:

- `LLAMA_CLOUD_ENABLED=true` selects LlamaParse for PDFs.
- `LLAMA_LOCAL_FALLBACK_ENABLED=true` preserves local fallback.
- Documents marked `needs_review` are not indexed by default.

Until A/B evidence is complete, production should prefer selective routing:
use Llama-first for complex PDFs, scanned documents, tables and forms; keep
simple Markdown/local paths available.

## Consequences

This branch can continue implementing the Llama-first path without forcing all
documents through cloud services or indexing unapproved bundles.
