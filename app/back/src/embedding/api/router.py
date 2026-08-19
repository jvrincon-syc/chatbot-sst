"""HTTP routes for the Embedding API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, status

from api.dependencies import get_authenticated_principal, require_project_access
from core.api.http import (
    DEFAULT_PAGE_SIZE,
    ErrorEnvelopeSchema,
    MAX_PAGE_SIZE,
    http_error,
    paginate,
)
from core.http_auth import project_in_scope
from core.feature_flags import FeatureFlags
from embedding.api.schemas import (
    ChunkBundleSummarySchema,
    EmbeddingBundleSchema,
    EmbeddingBundleValidationSchema,
    EmbeddingIndexingReadinessSchema,
    EmbeddingRunRequestSchema,
    EmbeddingRunSchema,
    PaginatedBundleChunksSchema,
    PaginatedChunkBundlesSchema,
    PaginatedEmbeddingRunsSchema,
    PaginatedProfilesSchema,
    PaginatedRuntimeSchema,
)
from embedding.application.read_service import EmbeddingReadService
from embedding.application.run_service import (
    CreateEmbeddingRunRequest,
    CreateEmbeddingRunUseCase,
    EmbeddingRunExecutor,
)
from embedding.domain.errors import EmbeddingDomainError


router = APIRouter(
    prefix="/api/embedding",
    tags=["embedding"],
    responses={
        400: {"model": ErrorEnvelopeSchema},
        404: {"model": ErrorEnvelopeSchema},
        409: {"model": ErrorEnvelopeSchema},
        422: {"model": ErrorEnvelopeSchema},
        429: {"model": ErrorEnvelopeSchema},
        503: {"model": ErrorEnvelopeSchema},
    },
)


def get_read_service(request: Request) -> EmbeddingReadService:
    """Return the read service bound to the running application."""

    return request.app.state.embedding_read_service


def get_create_run_use_case(request: Request) -> CreateEmbeddingRunUseCase:
    """Return the run creation use case bound to the running application."""

    return request.app.state.embedding_create_run


def get_executor(request: Request) -> EmbeddingRunExecutor:
    """Return the bounded run executor bound to the running application."""

    return request.app.state.embedding_executor


def get_feature_flags(request: Request) -> FeatureFlags:
    """Return the rollout flags bound to the running application."""

    return request.app.state.feature_flags


def _translate(error: EmbeddingDomainError, *, run_id: str | None = None):
    return http_error(
        status_code=error.http_status,
        code=error.code,
        message=str(error),
        run_id=run_id,
    )


def _visible_embedding_run_ids(request: Request) -> set[str] | None:
    principal = get_authenticated_principal(request)
    if principal.project_scope is None:
        return None
    return {
        run.embedding_run_id
        for run in request.app.state.embedding_runs.list_runs()
        if project_in_scope(principal, run.project_id)
    }


def _visible_chunk_bundle_ids(request: Request) -> set[str] | None:
    principal = get_authenticated_principal(request)
    if principal.project_scope is None:
        return None
    return {
        bundle.chunk_bundle_id
        for bundle in request.app.state.chunk_bundles.list_bundles()
        if project_in_scope(principal, bundle.project_id)
    }


@router.get("/profiles", response_model=PaginatedProfilesSchema)
def list_profiles(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    service: EmbeddingReadService = Depends(get_read_service),
) -> dict:
    return paginate(service.list_profiles(), page=page, page_size=page_size)


@router.get("/runtime", response_model=PaginatedRuntimeSchema)
def list_runtime(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    service: EmbeddingReadService = Depends(get_read_service),
) -> dict:
    return paginate(service.list_runtime(), page=page, page_size=page_size)


@router.get("/chunk-bundles", response_model=PaginatedChunkBundlesSchema)
def list_chunk_bundles(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    service: EmbeddingReadService = Depends(get_read_service),
) -> dict:
    items = service.list_chunk_bundles()
    visible_ids = _visible_chunk_bundle_ids(request)
    if visible_ids is not None:
        items = [item for item in items if item["chunk_bundle_id"] in visible_ids]
    return paginate(items, page=page, page_size=page_size)


@router.get(
    "/chunk-bundles/{chunk_bundle_id}/summary",
    response_model=ChunkBundleSummarySchema,
)
def get_chunk_bundle_summary(
    request: Request,
    chunk_bundle_id: str,
    service: EmbeddingReadService = Depends(get_read_service),
) -> dict:
    try:
        bundle = request.app.state.chunk_bundles.get(chunk_bundle_id)
        require_project_access(request, project_id=bundle.project_id)
        return service.get_chunk_bundle_summary(chunk_bundle_id)
    except EmbeddingDomainError as error:
        raise _translate(error) from error


@router.post(
    "/runs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=EmbeddingRunSchema,
)
def create_run(
    request: Request,
    payload: EmbeddingRunRequestSchema,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    use_case: CreateEmbeddingRunUseCase = Depends(get_create_run_use_case),
    executor: EmbeddingRunExecutor = Depends(get_executor),
    service: EmbeddingReadService = Depends(get_read_service),
    flags: FeatureFlags = Depends(get_feature_flags),
) -> dict:
    if not flags.embedding_v2:
        raise http_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="EMBEDDING_V2_DISABLED",
            message="the embedding_v2 feature flag is off",
        )
    try:
        chunk_bundle = request.app.state.chunk_bundles.get(payload.chunk_bundle_id)
        require_project_access(request, project_id=chunk_bundle.project_id)
        run = use_case.execute(
            request=CreateEmbeddingRunRequest(
                chunk_bundle_id=payload.chunk_bundle_id,
                profile_id=payload.profile_id,
            ),
            idempotency_key=idempotency_key,
        )
        if run.status == "pending":
            executor.submit(run.embedding_run_id)
    except EmbeddingDomainError as error:
        raise _translate(error) from error
    return service.get_run(run.embedding_run_id)


@router.get("/runs", response_model=PaginatedEmbeddingRunsSchema)
def list_runs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    service: EmbeddingReadService = Depends(get_read_service),
) -> dict:
    items = service.list_runs()
    visible_ids = _visible_embedding_run_ids(request)
    if visible_ids is not None:
        items = [item for item in items if item["embedding_run_id"] in visible_ids]
    return paginate(items, page=page, page_size=page_size)


@router.get("/runs/{embedding_run_id}", response_model=EmbeddingRunSchema)
def get_run(
    request: Request,
    embedding_run_id: str,
    service: EmbeddingReadService = Depends(get_read_service),
) -> dict:
    try:
        run = request.app.state.embedding_runs.get(embedding_run_id)
        require_project_access(request, project_id=run.project_id)
        return service.get_run(embedding_run_id)
    except EmbeddingDomainError as error:
        raise _translate(error, run_id=embedding_run_id) from error


@router.get("/bundles/{embedding_bundle_id}", response_model=EmbeddingBundleSchema)
def get_bundle(
    request: Request,
    embedding_bundle_id: str,
    service: EmbeddingReadService = Depends(get_read_service),
) -> dict:
    try:
        bundle = request.app.state.embedding_bundles.get(embedding_bundle_id)
        require_project_access(request, project_id=bundle.project_id)
        return service.get_bundle(embedding_bundle_id)
    except EmbeddingDomainError as error:
        raise _translate(error) from error


@router.get(
    "/bundles/{embedding_bundle_id}/chunks",
    response_model=PaginatedBundleChunksSchema,
)
def list_bundle_chunks(
    request: Request,
    embedding_bundle_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    service: EmbeddingReadService = Depends(get_read_service),
) -> dict:
    try:
        bundle = request.app.state.embedding_bundles.get(embedding_bundle_id)
        require_project_access(request, project_id=bundle.project_id)
        chunks = service.list_bundle_chunks(embedding_bundle_id)
    except EmbeddingDomainError as error:
        raise _translate(error) from error
    return paginate(chunks, page=page, page_size=page_size)


@router.get(
    "/bundles/{embedding_bundle_id}/validation",
    response_model=EmbeddingBundleValidationSchema,
)
def get_bundle_validation(
    request: Request,
    embedding_bundle_id: str,
    service: EmbeddingReadService = Depends(get_read_service),
) -> dict:
    try:
        bundle = request.app.state.embedding_bundles.get(embedding_bundle_id)
        require_project_access(request, project_id=bundle.project_id)
        return service.get_bundle_validation(embedding_bundle_id)
    except EmbeddingDomainError as error:
        raise _translate(error) from error


@router.get(
    "/bundles/{embedding_bundle_id}/indexing-readiness",
    response_model=EmbeddingIndexingReadinessSchema,
)
def get_bundle_indexing_readiness(
    request: Request,
    embedding_bundle_id: str,
    service: EmbeddingReadService = Depends(get_read_service),
) -> dict:
    try:
        bundle = request.app.state.embedding_bundles.get(embedding_bundle_id)
        require_project_access(request, project_id=bundle.project_id)
        return service.get_bundle_indexing_readiness(embedding_bundle_id)
    except EmbeddingDomainError as error:
        raise _translate(error) from error
