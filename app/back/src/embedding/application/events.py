"""Structured observability for the embedding, indexing and retrieval flows.

Every attribute passed through here is a scalar identifier or a count. Vectors,
document text, credentials, raw provider payloads and absolute paths never reach
an event: ``sanitize_observability_value`` would redact most of them, but the
call sites simply never build them.
"""

from __future__ import annotations

import logging
from typing import Mapping

from core.logging.observability import (
    EventContext,
    EventStatus,
    JsonScalar,
    ObservabilityDomain,
    ObservabilityEvent,
    emit_observability_event,
)


def emit_pipeline_event(
    *,
    logger: logging.Logger,
    domain: ObservabilityDomain,
    event: str,
    status: EventStatus,
    message: str,
    run_id: str | None = None,
    document_id: str | None = None,
    profile_id: str | None = None,
    provider: str | None = None,
    capability: str | None = None,
    configuration_hash: str | None = None,
    metrics: Mapping[str, int | float] | None = None,
    attributes: Mapping[str, JsonScalar] | None = None,
    exception: BaseException | None = None,
) -> None:
    """Emit one sanitized structured event for a bundle-first pipeline step."""

    emit_observability_event(
        logger=logger,
        event=ObservabilityEvent(
            event=event,
            domain=domain,
            status=status,
            message=message,
            context=EventContext(
                run_id=run_id,
                document_id=document_id,
                profile_id=profile_id,
                provider=provider,
                capability=capability,
                configuration_hash=configuration_hash,
            ),
            metrics=dict(metrics or {}),
            attributes=dict(attributes or {}),
        ),
        exception=exception,
    )
