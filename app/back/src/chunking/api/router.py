from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from chunking.api.dependencies import get_run_service
from chunking.api.schemas import (
    ChunkingProfileSchema,
    ChunkingRunAcceptedSchema,
    PaginatedStoredDocumentsSchema,
    PaginatedChildChunksSchema,
    PaginatedParentChunksSchema,
    ChunkingRunStatusSchema,
    ChunkingValidationSchema,
    ChunkingRunRequestSchema,
    ErrorEnvelopeSchema,
    PaginatedItemsSchema,
)
from chunking.application.run_service import (
    ChunkingDocumentNotFoundError,
    ChunkingIdempotencyConflictError,
    ChunkingParentNotFoundError,
    ChunkingProfileNotFoundError,
    ChunkingRunNotFoundError,
    ChunkingRunRequest,
    ChunkingRunService,
)


router = APIRouter(
    prefix="/api/chunking",
    tags=["chunking"],
    responses={
        400: {"model": ErrorEnvelopeSchema},
        404: {"model": ErrorEnvelopeSchema},
        409: {"model": ErrorEnvelopeSchema},
        422: {"model": ErrorEnvelopeSchema},
        500: {"model": ErrorEnvelopeSchema},
    },
)


def _http_error(
    *,
    status_code: int,
    code: str,
    message: str,
    run_id: str | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=ErrorEnvelopeSchema(
            error={
                "code": code,
                "message": message,
                "run_id": run_id,
                "details": {},
            }
        ).model_dump(),
    )


@router.get("/profiles", response_model=list[ChunkingProfileSchema])
def list_profiles(service: ChunkingRunService = Depends(get_run_service)) -> list[dict]:
    return service.list_profiles()


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED, response_model=ChunkingRunAcceptedSchema)
def create_run(
    payload: ChunkingRunRequestSchema,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    service: ChunkingRunService = Depends(get_run_service),
) -> dict:
    try:
        state = service.create_run(
            request=ChunkingRunRequest(
                scope=payload.scope,
                document_ids=tuple(payload.document_ids),
                profile_id=payload.profile_id,
                force=payload.force,
                request_id=request_id,
            ),
            idempotency_key=idempotency_key,
        )
    except ChunkingIdempotencyConflictError as error:
        raise _http_error(
            status_code=status.HTTP_409_CONFLICT,
            code="CHUNKING_IDEMPOTENCY_CONFLICT",
            message=str(error),
        ) from error
    except ChunkingDocumentNotFoundError as error:
        raise _http_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHUNKING_DOCUMENT_NOT_FOUND",
            message=str(error),
        ) from error
    except ChunkingProfileNotFoundError as error:
        raise _http_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHUNKING_PROFILE_NOT_FOUND",
            message=str(error),
        ) from error
    except ValueError as error:
        raise _http_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="CHUNKING_INVALID_REQUEST",
            message=str(error),
        ) from error

    service.submit_run(state.run_id)
    return service.get_run_payload(state.run_id)


@router.get("/runs/{run_id}", response_model=ChunkingRunStatusSchema)
def get_run(run_id: str, service: ChunkingRunService = Depends(get_run_service)) -> dict:
    try:
        return service.get_run_payload(run_id)
    except ChunkingRunNotFoundError as error:
        raise _http_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHUNKING_RUN_NOT_FOUND",
            message=str(error),
            run_id=run_id,
        ) from error


@router.get("/runs/{run_id}/documents", response_model=PaginatedItemsSchema)
def list_run_documents(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    service: ChunkingRunService = Depends(get_run_service),
) -> dict:
    try:
        return service.list_run_documents(run_id=run_id, page=page, page_size=page_size)
    except ChunkingRunNotFoundError as error:
        raise _http_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHUNKING_RUN_NOT_FOUND",
            message=str(error),
            run_id=run_id,
        ) from error


@router.get("/documents", response_model=PaginatedStoredDocumentsSchema)
def list_stored_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    service: ChunkingRunService = Depends(get_run_service),
) -> dict:
    return service.list_stored_documents(page=page, page_size=page_size)


@router.get("/runs/{run_id}/validation", response_model=ChunkingValidationSchema)
def get_validation(run_id: str, service: ChunkingRunService = Depends(get_run_service)) -> dict:
    try:
        return service.get_validation(run_id)
    except ChunkingRunNotFoundError as error:
        raise _http_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHUNKING_RUN_NOT_FOUND",
            message=str(error),
            run_id=run_id,
        ) from error


@router.get("/documents/{document_id}/parents", response_model=PaginatedParentChunksSchema)
def list_parents(
    document_id: str,
    run_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    service: ChunkingRunService = Depends(get_run_service),
) -> dict:
    try:
        return service.list_parents(
            document_id=document_id,
            run_id=run_id,
            page=page,
            page_size=page_size,
        )
    except ChunkingRunNotFoundError as error:
        raise _http_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHUNKING_RUN_NOT_FOUND",
            message=str(error),
            run_id=run_id,
        ) from error
    except ChunkingDocumentNotFoundError as error:
        raise _http_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHUNKING_DOCUMENT_NOT_FOUND",
            message=str(error),
        ) from error


@router.get("/parents/{parent_id}/children", response_model=PaginatedChildChunksSchema)
def list_children(
    parent_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    service: ChunkingRunService = Depends(get_run_service),
) -> dict:
    try:
        return service.list_children(parent_id=parent_id, page=page, page_size=page_size)
    except ChunkingParentNotFoundError as error:
        raise _http_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CHUNKING_PARENT_NOT_FOUND",
            message=str(error),
        ) from error
