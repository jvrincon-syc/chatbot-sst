"""Shared HTTP contract helpers: error envelope and page envelope.

The envelope shape is identical to the one Chunking already publishes, so the
frontend can reuse a single error and pagination handler across every domain.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from fastapi import HTTPException
from pydantic import Field

from ingestion.schemas.common import StrictModel


ItemT = TypeVar("ItemT")

#: Largest page a listing endpoint will ever return.
MAX_PAGE_SIZE = 100

#: Default page size when the caller does not ask for one.
DEFAULT_PAGE_SIZE = 25


class ErrorBodySchema(StrictModel):
    """Body of the shared error envelope."""

    code: str
    message: str
    run_id: str | None = None
    details: dict[str, object] = Field(default_factory=dict)


class ErrorEnvelopeSchema(StrictModel):
    """Every non-2xx response uses this envelope."""

    error: ErrorBodySchema


def http_error(
    *,
    status_code: int,
    code: str,
    message: str,
    run_id: str | None = None,
    details: dict[str, object] | None = None,
) -> HTTPException:
    """Build an ``HTTPException`` already carrying the shared envelope."""

    return HTTPException(
        status_code=status_code,
        detail=ErrorEnvelopeSchema(
            error=ErrorBodySchema(
                code=code,
                message=message,
                run_id=run_id,
                details=details or {},
            )
        ).model_dump(),
    )


def paginate(
    items: Sequence[ItemT],
    *,
    page: int,
    page_size: int,
) -> dict[str, object]:
    """Return one page of an already-materialized sequence."""

    total_items = len(items)
    total_pages = (total_items + page_size - 1) // page_size if total_items else 0
    start = (page - 1) * page_size
    return {
        "items": list(items[start : start + page_size]),
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
    }
