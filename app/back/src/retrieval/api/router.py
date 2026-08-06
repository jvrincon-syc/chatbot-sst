"""HTTP routes for the Retrieval API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status

from core.api.http import (
    DEFAULT_PAGE_SIZE,
    ErrorEnvelopeSchema,
    MAX_PAGE_SIZE,
    http_error,
    paginate,
)
from core.feature_flags import FeatureFlags
from embedding.domain.errors import EmbeddingDomainError
from retrieval.api.schemas import (
    CreateRetrievalProfileSchema,
    PaginatedRetrievalProfilesSchema,
    RetrievalProfileSchema,
    RetrievalProfileStatusSchema,
    RetrievalValidationSchema,
    ValidateRetrievalSchema,
)
from retrieval.application.ports import RetrievalProfileRepository
from retrieval.application.retrieval_service import (
    ActivateRetrievalProfileUseCase,
    CreateRetrievalProfileRequest,
    CreateRetrievalProfileUseCase,
    GetRetrievalProfileStatusUseCase,
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


def get_feature_flags(request: Request) -> FeatureFlags:
    """Return the rollout flags bound to the application."""

    return request.app.state.feature_flags


def _translate(error: Exception):
    return http_error(
        status_code=int(getattr(error, "http_status", 400)),
        code=getattr(error, "code", "RETRIEVAL_DOMAIN_ERROR"),
        message=str(error),
    )


def _profile_payload(profile: RetrievalProfile) -> dict[str, object]:
    return profile.model_dump(mode="json")


@router.get("/profiles", response_model=PaginatedRetrievalProfilesSchema)
def list_profiles(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    profiles: RetrievalProfileRepository = Depends(get_profiles),
) -> dict:
    items = [_profile_payload(profile) for profile in profiles.list_profiles()]
    return paginate(items, page=page, page_size=page_size)


@router.post(
    "/profiles",
    status_code=status.HTTP_201_CREATED,
    response_model=RetrievalProfileSchema,
)
def create_profile(
    payload: CreateRetrievalProfileSchema,
    use_case: CreateRetrievalProfileUseCase = Depends(get_create_use_case),
    flags: FeatureFlags = Depends(get_feature_flags),
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
                consumer_scope_type=payload.consumer_scope_type,
                consumer_scope_id=payload.consumer_scope_id,
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
        profile = use_case.execute(retrieval_profile_id)
    except _DOMAIN_ERRORS as error:
        raise _translate(error) from error
    return _profile_payload(profile)


@router.get(
    "/profiles/{retrieval_profile_id}/status",
    response_model=RetrievalProfileStatusSchema,
)
def get_profile_status(
    retrieval_profile_id: str,
    use_case: GetRetrievalProfileStatusUseCase = Depends(get_status_use_case),
) -> dict:
    try:
        return use_case.execute(retrieval_profile_id)
    except _DOMAIN_ERRORS as error:
        raise _translate(error) from error


@router.post("/validate", response_model=RetrievalValidationSchema)
def validate_retrieval(
    payload: ValidateRetrievalSchema,
    use_case: ValidateRetrievalUseCase = Depends(get_validate_use_case),
) -> dict:
    try:
        return use_case.execute(payload.retrieval_profile_id).model_dump()
    except _DOMAIN_ERRORS as error:
        raise _translate(error) from error
