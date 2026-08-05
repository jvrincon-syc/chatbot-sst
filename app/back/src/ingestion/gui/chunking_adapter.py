from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from chunking.api.dependencies import build_run_service
from chunking.application.run_service import (
    ChunkingDocumentNotFoundError,
    ChunkingIdempotencyConflictError,
    ChunkingParentNotFoundError,
    ChunkingProfileNotFoundError,
    ChunkingRunNotFoundError,
    ChunkingRunRequest,
    ChunkingRunService,
)


logger = logging.getLogger(__name__)


def _chunking_error_payload(
    *,
    code: str,
    message: str,
    run_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "run_id": run_id,
            "details": details or {},
        }
    }


def _query_int(
    query: dict[str, list[str]],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    values = query.get(name) or []
    if not values or values[0].strip() == "":
        return default
    try:
        value = int(values[0])
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < minimum:
        raise ValueError(f"{name} must be greater than or equal to {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be less than or equal to {maximum}")
    return value


class ChunkingApiBridge:
    """Expose the chunking HTTP contract through the existing GUI server."""

    def __init__(self, *, docs_normalized: Path, chunks_root: Path) -> None:
        self._service: ChunkingRunService = build_run_service(
            docs_normalized=docs_normalized,
            chunks_root=chunks_root,
        )

    def close(self) -> None:
        self._service.close()

    def handle_get(self, path: str) -> tuple[int, Any]:
        parsed = urlparse(path)
        route = parsed.path.removeprefix("/api/chunking")
        query = parse_qs(parsed.query)
        segments = [segment for segment in route.split("/") if segment]

        try:
            if route == "/profiles":
                return int(HTTPStatus.OK), self._service.list_profiles()

            if len(segments) == 2 and segments[0] == "runs":
                return int(HTTPStatus.OK), self._service.get_run_payload(segments[1])

            if len(segments) == 3 and segments[0] == "runs" and segments[2] == "documents":
                page = _query_int(query, "page", 1, minimum=1)
                page_size = _query_int(query, "page_size", 25, minimum=1, maximum=100)
                return int(HTTPStatus.OK), self._service.list_run_documents(
                    run_id=segments[1],
                    page=page,
                    page_size=page_size,
                )

            if len(segments) == 3 and segments[0] == "runs" and segments[2] == "validation":
                return int(HTTPStatus.OK), self._service.get_validation(segments[1])

            if len(segments) == 3 and segments[0] == "documents" and segments[2] == "parents":
                page = _query_int(query, "page", 1, minimum=1)
                page_size = _query_int(query, "page_size", 25, minimum=1, maximum=100)
                run_id = self._single_query_value(query, "run_id")
                return int(HTTPStatus.OK), self._service.list_parents(
                    document_id=segments[1],
                    run_id=run_id,
                    page=page,
                    page_size=page_size,
                )

            if len(segments) == 3 and segments[0] == "parents" and segments[2] == "children":
                page = _query_int(query, "page", 1, minimum=1)
                page_size = _query_int(query, "page_size", 25, minimum=1, maximum=100)
                return int(HTTPStatus.OK), self._service.list_children(
                    parent_id=segments[1],
                    page=page,
                    page_size=page_size,
                )

            return int(HTTPStatus.NOT_FOUND), _chunking_error_payload(
                code="CHUNKING_ROUTE_NOT_FOUND",
                message="endpoint not found",
            )
        except ChunkingRunNotFoundError as error:
            return int(HTTPStatus.NOT_FOUND), _chunking_error_payload(
                code="CHUNKING_RUN_NOT_FOUND",
                message=str(error),
                run_id=segments[1] if len(segments) > 1 and segments[0] == "runs" else None,
            )
        except ChunkingDocumentNotFoundError as error:
            return int(HTTPStatus.NOT_FOUND), _chunking_error_payload(
                code="CHUNKING_DOCUMENT_NOT_FOUND",
                message=str(error),
            )
        except ChunkingParentNotFoundError as error:
            return int(HTTPStatus.NOT_FOUND), _chunking_error_payload(
                code="CHUNKING_PARENT_NOT_FOUND",
                message=str(error),
            )
        except ValueError as error:
            return int(HTTPStatus.BAD_REQUEST), _chunking_error_payload(
                code="CHUNKING_INVALID_REQUEST",
                message=str(error),
            )

    def handle_post(
        self,
        path: str,
        body: Any,
        headers: dict[str, str],
        *,
        request_id: str | None = None,
    ) -> tuple[int, Any]:
        parsed = urlparse(path)
        route = parsed.path.removeprefix("/api/chunking")
        segments = [segment for segment in route.split("/") if segment]

        if len(segments) != 1 or segments[0] != "runs":
            return int(HTTPStatus.NOT_FOUND), _chunking_error_payload(
                code="CHUNKING_ROUTE_NOT_FOUND",
                message="endpoint not found",
            )

        idempotency_key = headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            return int(HTTPStatus.UNPROCESSABLE_ENTITY), _chunking_error_payload(
                code="CHUNKING_INVALID_REQUEST",
                message="Idempotency-Key header is required",
            )

        if not isinstance(body, dict):
            return int(HTTPStatus.BAD_REQUEST), _chunking_error_payload(
                code="CHUNKING_INVALID_REQUEST",
                message="request body must be a JSON object",
            )

        document_ids_raw = body.get("document_ids", [])
        if document_ids_raw is None:
            document_ids_raw = []
        if not isinstance(document_ids_raw, list):
            return int(HTTPStatus.BAD_REQUEST), _chunking_error_payload(
                code="CHUNKING_INVALID_REQUEST",
                message="document_ids must be a list",
            )

        scope = body.get("scope", "")
        profile_id = body.get("profile_id", "")
        force = body.get("force", False)
        if not isinstance(scope, str) or not isinstance(profile_id, str) or not isinstance(force, bool):
            return int(HTTPStatus.BAD_REQUEST), _chunking_error_payload(
                code="CHUNKING_INVALID_REQUEST",
                message="scope, profile_id and force must have the expected types",
            )

        try:
            state = self._service.create_run(
                request=ChunkingRunRequest(
                    scope=scope,
                    document_ids=tuple(str(item) for item in document_ids_raw),
                    profile_id=profile_id,
                    force=force,
                    request_id=request_id,
                ),
                idempotency_key=idempotency_key,
            )
            self._service.submit_run(state.run_id)
            return int(HTTPStatus.ACCEPTED), self._service.get_run_payload(state.run_id)
        except ChunkingIdempotencyConflictError as error:
            return int(HTTPStatus.CONFLICT), _chunking_error_payload(
                code="CHUNKING_IDEMPOTENCY_CONFLICT",
                message=str(error),
            )
        except ChunkingDocumentNotFoundError as error:
            return int(HTTPStatus.NOT_FOUND), _chunking_error_payload(
                code="CHUNKING_DOCUMENT_NOT_FOUND",
                message=str(error),
            )
        except ChunkingProfileNotFoundError as error:
            return int(HTTPStatus.NOT_FOUND), _chunking_error_payload(
                code="CHUNKING_PROFILE_NOT_FOUND",
                message=str(error),
            )
        except ValueError as error:
            return int(HTTPStatus.BAD_REQUEST), _chunking_error_payload(
                code="CHUNKING_INVALID_REQUEST",
                message=str(error),
            )
        except Exception as error:  # pragma: no cover - defensive guard
            logger.exception(
                "chunking_gui_bridge_failed",
                extra={"route": "/api/chunking", "request_id": request_id},
            )
            return int(HTTPStatus.INTERNAL_SERVER_ERROR), _chunking_error_payload(
                code="CHUNKING_INTERNAL_ERROR",
                message=str(error),
            )

    @staticmethod
    def _single_query_value(query: dict[str, list[str]], name: str) -> str | None:
        values = query.get(name) or []
        if not values:
            return None
        value = values[0].strip()
        return value or None
