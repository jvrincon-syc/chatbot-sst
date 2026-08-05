# Llama Credit Exhaustion Runbook

## Trigger

The configured run budget is near or above `LLAMA_PARSE_MAX_CREDITS_PER_RUN`.

## Response

1. Stop starting new cloud jobs.
2. Allow already-submitted jobs to finish if cancellation would lose evidence.
3. Switch to local fallback for remaining documents.
4. Record affected documents and capabilities in the provider run log.

## Recovery

Increase budget only after reviewing document count, page count, tier and
whether cached parse results can be reused.
