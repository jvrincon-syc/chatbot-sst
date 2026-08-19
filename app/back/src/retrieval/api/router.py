"""HTTP routes for the Retrieval API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status

from api.dependencies import get_authenticated_principal, require_project_access
from core.api.http import (
    DEFAULT_PAGE_SIZE,
    ErrorEnvelopeSchema,
    MAX_PAGE_SIZE,
    http_error,
    paginate,
)
from core.consumer_scope import ConsumerScope
from core.feature_flags import FeatureFlags
from core.http_auth import project_in_scope
from embedding.domain.errors import EmbeddingDomainError
from retrieval.api.schemas import (
    CreateRetrievalProfileSchema,
    PaginatedRetrievalProfilesSchema,
    RetrievalProfileSchema,
    RetrievalProfileStatusSchema,
    RetrievalSearchResponseSchema,
    RetrievalValidationSchema,
    SearchRetrievalSchema,
    ValidateRetrievalSchema,
)
from retrieval.application.ports import RetrievalProfileRepository
from retrieval.application.retrieval_service import (
    ActivateRetrievalProfileUseCase,
    CreateRetrievalProfileRequest,
    CreateRetrievalProfileUseCase,
    GetRetrievalProfileStatusUseCase,
    SearchRetrievalRequest,
    SearchRetrievalUseCase,
    ValidateRetrievalUseCase,
)
from retrieval.domain.errors import RetrievalDomainError
from retrieval.domain.models import RetrievalProfile


router = APIRouter(
    prefix="/api/retrieval",
    tags=["retrieval"],
    responses={
        400: {"model": ErrorEnvelopeSchema},
        404: {"model": ErrorEnvelopeSchema},
        409: {"model": ErrorEnvelopeSchema},
        422: {"model": ErrorEnvelopeSchema},
        503: {"model": ErrorEnvelopeSchema},
    },
)

_DOMAIN_ERRORS = (EmbeddingDomainError, RetrievalDomainError)


def get_profiles(request: Request) -> RetrievalProfileRepository:
    """Return the retrieval profile repository bound to the application."""

    return request.app.state.retrieval_profiles


def get_create_use_case(request: Request) -> CreateRetrievalProfileUseCase:
    """Return the profile creation use case bound to the application."""

    return request.app.state.retrieval_create_profile


def get_activate_use_case(request: Request) -> ActivateRetrievalProfileUseCase:
    """Return the activation use case bound to the application."""

    return request.app.state.retrieval_activate_profile


def get_status_use_case(request: Request) -> GetRetrievalProfileStatusUseCase:
    """Return the status use case bound to the application."""

    return request.app.state.retrieval_profile_status


def get_validate_use_case(request: Request) -> ValidateRetrievalUseCase:
    """Return the validation use case bound to the application."""

    return request.app.state.retrieval_validate


def get_search_use_case(request: Request) -> SearchRetrievalUseCase:
    """Return the search use case bound to the application."""

    return request.app.state.retrieval_search


def get_feature_flags(request: Request) -> FeatureFlags:
    """Return the rollout flags bound to the application."""

    return request.app.state.feature_flags


def get_consumer_scope(request: Request) -> ConsumerScope:
    """Return the server-controlled consumer scope for retrieval mutations."""

    return request.app.state.consumer_scope


def _translate(error: Exception):
    return http_error(
        status_code=int(getattr(error, "http_status", 400)),
        code=getattr(error, "code", "RETRIEVAL_DOMAIN_ERROR"),
        message=str(error),
    )


def _profile_payload(profile: RetrievalProfile) -> dict[str, object]:
    payload = profile.model_dump(mode="json")
    payload.pop("project_id", None)
    return payload


def _resolve_project_id_for_corpus(request: Request, *, corpus_version: str) -> str:
    """Resolve the owning project from registered chunk bundles, or fail closed."""

    principal = get_authenticated_principal(request)
    bundles = request.app.state.chunk_bundles.list_bundles()
    project_ids = {
        bundle.project_id
        for bundle in bundles
        if bundle.corpus_version == corpus_version
    }
    if len(project_ids) == 1:
        return next(iter(project_ids))
    if not project_ids:
        raise http_error(
            status_code=status.HTTP_409_CONFLICT,
            code="RETRIEVAL_PROJECT_CONTEXT_UNAVAILABLE",
            message=(
                "no registered project owns the requested corpus_version; "
                "retrieval profile creation is blocked fail-closed"
            ),
        )
    visible_project_ids = {
        project_id for project_id in project_ids if project_in_scope(principal, project_id)
    }
    if not visible_project_ids:
        require_project_access(request, project_id=next(iter(sorted(project_ids))))
    if len(visible_project_ids) == 1:
        return next(iter(visible_project_ids))
    raise http_error(
        status_code=status.HTTP_409_CONFLICT,
        code="RETRIEVAL_PROJECT_CONTEXT_AMBIGUOUS",
        message=(
            "multiple projects own the requested corpus_version; retrieval profile "
            "creation must not guess the project"
        ),
    )


@router.get("/profiles", response_model=PaginatedRetrievalProfilesSchema)
def list_profiles(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    profiles: RetrievalProfileRepository = Depends(get_profiles),
) -> dict:
    principal = get_authenticated_principal(request)
    items = [
        _profile_payload(profile)
        for profile in profiles.list_profiles()
        if project_in_scope(principal, profile.project_id)
    ]
    return paginate(items, page=page, page_size=page_size)


@router.post(
    "/profiles",
    status_code=status.HTTP_201_CREATED,
    response_model=RetrievalProfileSchema,
)
def create_profile(
    request: Request,
    payload: CreateRetrievalProfileSchema,
    use_case: CreateRetrievalProfileUseCase = Depends(get_create_use_case),
    flags: FeatureFlags = Depends(get_feature_flags),
    scope: ConsumerScope = Depends(get_consumer_scope),
) -> dict:
    if not flags.retrieval_v1:
        raise http_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="RETRIEVAL_V1_DISABLED",
            message="the retrieval_v1 feature flag is off",
        )
    try:
        profile = use_case.execute(
            CreateRetrievalProfileRequest(
                project_id=_resolve_project_id_for_corpus(
                    request,
                    corpus_version=payload.corpus_version,
                ),
                consumer_scope_type=scope.scope_type,
                consumer_scope_id=scope.scope_id,
                corpus_version=payload.corpus_version,
                embedding_profile_id=payload.embedding_profile_id,
                indexing_target_id=payload.indexing_target_id,
                lexical_fallback_policy=payload.lexical_fallback_policy,
            )
        )
    except _DOMAIN_ERRORS as error:
        raise _translate(error) from error
    return _profile_payload(profile)


@router.post(
    "/profiles/{retrieval_profile_id}/activate",
    response_model=RetrievalProfileSchema,
)
def activate_profile(
    request: Request,
    retrieval_profile_id: str,
    use_case: ActivateRetrievalProfileUseCase = Depends(get_activate_use_case),
    flags: FeatureFlags = Depends(get_feature_flags),
) -> dict:
    if not flags.retrieval_v1:
        raise http_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="RETRIEVAL_V1_DISABLED",
            message="the retrieval_v1 feature flag is off",
        )
    try:
        profile = request.app.state.retrieval_profiles.get(retrieval_profile_id)
        require_project_access(request, project_id=profile.project_id)
        profile = use_case.execute(retrieval_profile_id)
    except _DOMAIN_ERRORS as error:
        raise _translate(error) from error
    return _profile_payload(profile)


@router.get(
    "/profiles/{retrieval_profile_id}/status",
    response_model=RetrievalProfileStatusSchema,
)
def get_profile_status(
    request: Request,
    retrieval_profile_id: str,
    use_case: GetRetrievalProfileStatusUseCase = Depends(get_status_use_case),
) -> dict:
    try:
        profile = request.app.state.retrieval_profiles.get(retrieval_profile_id)
        require_project_access(request, project_id=profile.project_id)
        payload = use_case.execute(retrieval_profile_id)
    except _DOMAIN_ERRORS as error:
        raise _translate(error) from error
    payload["profile"].pop("project_id", None)
    return payload


@router.post("/validate", response_model=RetrievalValidationSchema)
def validate_retrieval(
    request: Request,
    payload: ValidateRetrievalSchema,
    use_case: ValidateRetrievalUseCase = Depends(get_validate_use_case),
) -> dict:
    try:
        profile = request.app.state.retrieval_profiles.get(payload.retrieval_profile_id)
        require_project_access(request, project_id=profile.project_id)
        return use_case.execute(payload.retrieval_profile_id).model_dump()
    except _DOMAIN_ERRORS as error:
        raise _translate(error) from error


@router.post("/search", response_model=RetrievalSearchResponseSchema)
def search_retrieval(
    request: Request,
    payload: SearchRetrievalSchema,
    use_case: SearchRetrievalUseCase = Depends(get_search_use_case),
) -> dict:
    try:
        profile = request.app.state.retrieval_profiles.get(payload.retrieval_profile_id)
        require_project_access(request, project_id=profile.project_id)
        items = use_case.execute(
            SearchRetrievalRequest(
                retrieval_profile_id=payload.retrieval_profile_id,
                query=payload.query,
                top_k=payload.top_k,
            )
        )
    except _DOMAIN_ERRORS as error:
        raise _translate(error) from error
    return {
        "retrieval_profile_id": payload.retrieval_profile_id,
        "top_k": payload.top_k,
        "items": [item.model_dump(mode="json") for item in items],
    }
