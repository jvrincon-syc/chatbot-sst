"""HTTP routes for the bundle-first Indexing API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, status

from core.api.http import (
    DEFAULT_PAGE_SIZE,
    ErrorEnvelopeSchema,
    MAX_PAGE_SIZE,
    http_error,
    paginate,
)
from core.consumer_scope import ConsumerScope
from core.feature_flags import FeatureFlags
from embedding.domain.errors import EmbeddingDomainError
from indexing.api.schemas import (
    ActivationRequestSchema,
    ActivationResultSchema,
    IndexingOverviewSchema,
    IndexingRetrievalReadinessSchema,
    IndexingRunRequestSchema,
    IndexingRunSchema,
    PaginatedIndexingRunsSchema,
    PaginatedRunDocumentsSchema,
    PaginatedRunErrorsSchema,
    PaginatedTargetsSchema,
    RollbackRequestSchema,
)
from indexing.application.bundle_first.activation import (
    ActivateIndexedBundleUseCase,
    ActivationRequest,
    RollbackIndexedBundleUseCase,
    RollbackRequest,
)
from indexing.application.bundle_first.index_bundle import (
    CreateIndexingRunRequest,
    CreateIndexingRunUseCase,
    IndexingRunExecutor,
)
from indexing.application.bundle_first.read_service import IndexingReadService
from indexing.domain.errors import IndexingDomainError
from retrieval.domain.errors import RetrievalDomainError


router = APIRouter(
    prefix="/api/indexing",
    tags=["indexing"],
    responses={
        400: {"model": ErrorEnvelopeSchema},
        404: {"model": ErrorEnvelopeSchema},
        409: {"model": ErrorEnvelopeSchema},
        422: {"model": ErrorEnvelopeSchema},
        429: {"model": ErrorEnvelopeSchema},
        503: {"model": ErrorEnvelopeSchema},
    },
)


def get_read_service(request: Request) -> IndexingReadService:
    """Return the read service bound to the running application."""

    return request.app.state.indexing_read_service


def get_create_run_use_case(request: Request) -> CreateIndexingRunUseCase:
    """Return the run creation use case bound to the running application."""

    return request.app.state.indexing_create_run


def get_executor(request: Request) -> IndexingRunExecutor:
    """Return the bounded run executor bound to the running application."""

    return request.app.state.indexing_executor


def get_activate_use_case(request: Request) -> ActivateIndexedBundleUseCase:
    """Return the activation use case bound to the running application."""

    return request.app.state.indexing_activate


def get_rollback_use_case(request: Request) -> RollbackIndexedBundleUseCase:
    """Return the rollback use case bound to the running application."""

    return request.app.state.indexing_rollback


def get_feature_flags(request: Request) -> FeatureFlags:
    """Return the rollout flags bound to the running application."""

    return request.app.state.feature_flags


def get_consumer_scope(request: Request) -> ConsumerScope:
    """Return the server-controlled consumer scope for mutations."""

    return request.app.state.consumer_scope


def _require_bundle_first(flags: FeatureFlags) -> None:
    """Fail closed when the bundle-first rollout flag is off."""

    if not flags.indexing_bundle_first:
        raise http_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="INDEXING_BUNDLE_FIRST_DISABLED",
            message="the indexing_bundle_first feature flag is off",
        )


def _translate(error: Exception, *, run_id: str | None = None):
    code = getattr(error, "code", "INDEXING_DOMAIN_ERROR")
    http_status = int(getattr(error, "http_status", 400))
    return http_error(
        status_code=http_status,
        code=code,
        message=str(error),
        run_id=run_id,
    )


_DOMAIN_ERRORS = (EmbeddingDomainError, IndexingDomainError, RetrievalDomainError)


@router.get("/overview", response_model=IndexingOverviewSchema)
def get_overview(service: IndexingReadService = Depends(get_read_service)) -> dict:
    return service.overview()


@router.get("/targets", response_model=PaginatedTargetsSchema)
def list_targets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    service: IndexingReadService = Depends(get_read_service),
) -> dict:
    return paginate(service.list_targets(), page=page, page_size=page_size)


@router.post(
    "/runs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IndexingRunSchema,
)
def create_run(
    payload: IndexingRunRequestSchema,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    use_case: CreateIndexingRunUseCase = Depends(get_create_run_use_case),
    executor: IndexingRunExecutor = Depends(get_executor),
    service: IndexingReadService = Depends(get_read_service),
    flags: FeatureFlags = Depends(get_feature_flags),
) -> dict:
    _require_bundle_first(flags)
    try:
        run = use_case.execute(
            request=CreateIndexingRunRequest(
                embedding_bundle_id=payload.embedding_bundle_id
            ),
            idempotency_key=idempotency_key,
        )
        if run.status == "pending":
            executor.submit(run.run_id)
    except _DOMAIN_ERRORS as error:
        raise _translate(error) from error
    return service.get_run(run.run_id)


@router.get("/runs", response_model=PaginatedIndexingRunsSchema)
def list_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    service: IndexingReadService = Depends(get_read_service),
) -> dict:
    return paginate(service.list_runs(), page=page, page_size=page_size)


@router.get("/runs/{run_id}", response_model=IndexingRunSchema)
def get_run(run_id: str, service: IndexingReadService = Depends(get_read_service)) -> dict:
    try:
        return service.get_run(run_id)
    except _DOMAIN_ERRORS as error:
        raise _translate(error, run_id=run_id) from error


@router.get("/runs/{run_id}/documents", response_model=PaginatedRunDocumentsSchema)
def list_run_documents(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    service: IndexingReadService = Depends(get_read_service),
) -> dict:
    try:
        documents = service.list_run_documents(run_id)
    except _DOMAIN_ERRORS as error:
        raise _translate(error, run_id=run_id) from error
    return paginate(documents, page=page, page_size=page_size)


@router.get("/runs/{run_id}/errors", response_model=PaginatedRunErrorsSchema)
def list_run_errors(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    service: IndexingReadService = Depends(get_read_service),
) -> dict:
    try:
        errors = service.list_run_errors(run_id)
    except _DOMAIN_ERRORS as error:
        raise _translate(error, run_id=run_id) from error
    return paginate(errors, page=page, page_size=page_size)


@router.get(
    "/runs/{run_id}/retrieval-readiness",
    response_model=IndexingRetrievalReadinessSchema,
)
def get_retrieval_readiness(
    run_id: str,
    service: IndexingReadService = Depends(get_read_service),
) -> dict:
    try:
        return service.get_retrieval_readiness(run_id)
    except _DOMAIN_ERRORS as error:
        raise _translate(error, run_id=run_id) from error


@router.post("/activations", response_model=ActivationResultSchema)
def activate_bundle(
    payload: ActivationRequestSchema,
    use_case: ActivateIndexedBundleUseCase = Depends(get_activate_use_case),
    flags: FeatureFlags = Depends(get_feature_flags),
    scope: ConsumerScope = Depends(get_consumer_scope),
) -> dict:
    _require_bundle_first(flags)
    try:
        result = use_case.execute(
            ActivationRequest(
                run_id=payload.run_id,
                consumer_scope_type=scope.scope_type,
                consumer_scope_id=scope.scope_id,
                lexical_fallback_policy=payload.lexical_fallback_policy,
            )
        )
    except _DOMAIN_ERRORS as error:
        raise _translate(error, run_id=payload.run_id) from error
    return {
        "run_id": result.run_id,
        "embedding_bundle_id": result.embedding_bundle_id,
        "indexing_target_id": result.indexing_target_id,
        "retrieval_profile_id": result.retrieval_profile_id,
        "activated_rows": result.activated_rows,
    }


@router.post("/rollbacks", response_model=ActivationResultSchema)
def rollback_bundle(
    payload: RollbackRequestSchema,
    use_case: RollbackIndexedBundleUseCase = Depends(get_rollback_use_case),
    flags: FeatureFlags = Depends(get_feature_flags),
    scope: ConsumerScope = Depends(get_consumer_scope),
) -> dict:
    _require_bundle_first(flags)
    try:
        result = use_case.execute(
            RollbackRequest(
                current_embedding_bundle_id=payload.current_embedding_bundle_id,
                previous_embedding_bundle_id=payload.previous_embedding_bundle_id,
                consumer_scope_type=scope.scope_type,
                consumer_scope_id=scope.scope_id,
            )
        )
    except _DOMAIN_ERRORS as error:
        raise _translate(error) from error
    return {
        "run_id": result.run_id,
        "embedding_bundle_id": result.embedding_bundle_id,
        "indexing_target_id": result.indexing_target_id,
        "retrieval_profile_id": result.retrieval_profile_id,
        "activated_rows": result.activated_rows,
    }
