# Llama-first Benchmark Report

Date: 2026-07-21

## Current Status

The benchmark harness is ready for local, non-live evaluation.

- Documents dataset: `data/evaluation/llama_first/documents.jsonl`
- Questions dataset: `data/evaluation/llama_first/questions.jsonl`
- Expected metadata: `data/evaluation/llama_first/expected_metadata.jsonl`
- Command: `npm run evaluation:llama-first`

## Current Result

Live cloud evaluation is intentionally disabled until the data authorization,
region, retention/deletion policy and credit budget are approved.

The current benchmark command verifies that the evaluation corpus is present and
bounded. Full A/B metrics require an indexed corpus and approved live or recorded
Llama fixtures.
