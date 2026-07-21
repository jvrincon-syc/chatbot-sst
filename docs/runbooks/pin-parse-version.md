# Pin Parse Version Runbook

## Trigger

Benchmark results are accepted and the experiment must stop using
`LLAMA_PARSE_VERSION=latest`.

## Response

1. Read the effective Parse version returned in job metadata.
2. Update `LLAMA_PARSE_VERSION` to the validated dated version.
3. Re-run the smoke document and benchmark subset.
4. Record result in `docs/llama_first/research-log.md` and ADR.

## Recovery

If output changes, keep the previous pin and route affected document types to
review or local fallback.
