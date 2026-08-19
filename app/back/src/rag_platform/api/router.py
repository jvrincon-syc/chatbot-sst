"""Rutas HTTP de la plataforma RAG multi-proyecto (Fase 7).

Adaptador HTTP **delgado** sobre ``services.rag_platform.*``: valida entrada
Pydantic, resuelve el actor de confianza server-side, aplica la guarda de
idempotencia donde corresponde y delega en el caso de uso ya cableado. El router
no ejecuta SQL, no calcula fingerprints, no resuelve tablas físicas ni deriva
``indexing_target_id``, y no importa repositorios concretos: toda esa autoridad
vive en la capa de aplicación.

La traducción de errores de dominio (``RagPlatformError``) al envelope HTTP es
**centralizada** en ``api/app.py`` (un solo ``exception_handler``); aquí no hay
``try/except RagPlatformError`` repetido por endpoint.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status

from core.api.http import (
    DEFAULT_PAGE_SIZE,
    ErrorEnvelopeSchema,
    MAX_PAGE_SIZE,
    http_error,
    paginate,
)
from rag_platform.api.dependencies import (
    get_actor_provider,
    get_idempotency_store,
    get_platform_services,
    require_rag_platform_enabled,
)
from rag_platform.api.schemas import (
    CorpusSnapshotSchema,
    CreateCorpusSnapshotRequestSchema,
    CreateProjectRequestSchema,
    CreateReleaseDraftRequestSchema,
    CreateVariantRequestSchema,
    PaginatedProjectsSchema,
    PaginatedVariantsSchema,
    ProjectConfigurationSchema,
    ProjectSchema,
    ReleaseBuildReportSchema,
    ReleaseSchema,
    RetireReleaseRequestSchema,
    UpdateProjectConfigurationRequestSchema,
    UpdateProjectRequestSchema,
    VariantMatrixCellSchema,
    VariantSchema,
    build_report_to_schema,
    configuration_to_schema,
    matrix_cell_to_schema,
    project_to_schema,
    release_to_schema,
    snapshot_to_schema,
    variant_to_schema,
)
from rag_platform.application.actor_provider import TrustedPlatformActorProvider
from rag_platform.application.idempotency import IdempotencyGuard, IdempotencyStore
from rag_platform.application.platform_access import PlatformActor
from rag_platform.application.variant_matrix_service import platform_id_body
from rag_platform.application.project_service import CreateProjectRequest
from rag_platform.application.project_configuration_service import (
    UpdateProjectConfigurationRequest,
)
from rag_platform.application.services import RagPlatformServices
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import EligibilityDecision


router = APIRouter(
    prefix="/api/platform",
    tags=["platform"],
    dependencies=[Depends(require_rag_platform_enabled)],
    responses={
        400: {"model": ErrorEnvelopeSchema},
        403: {"model": ErrorEnvelopeSchema},
        404: {"model": ErrorEnvelopeSchema},
        409: {"model": ErrorEnvelopeSchema},
        422: {"model": ErrorEnvelopeSchema},
        503: {"model": ErrorEnvelopeSchema},
    },
)

#: Header de idempotencia obligatorio en mutaciones de release.
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1)]


def get_actor(
    provider: TrustedPlatformActorProvider = Depends(get_actor_provider),
) -> PlatformActor:
    """Resuelve el ``PlatformActor`` de confianza (fail-closed si no hay actor)."""

    return provider.current_actor()


def _parse_id(kind: IdentityKind, value: str) -> PlatformId:
    """Parsea un ID (path o body) a ``PlatformId``.

    Un ID malformado lanza ``InvalidIdentity``, traducida a 422 estable por el
    handler central de ``api/app.py`` (mismo punto que los IDs construidos dentro
    de los casos de uso desde slugs de body). Sin traducción duplicada aquí.
    """

    return PlatformId.parse(kind, value)


def _eligibility_decisions(
    raw: dict[str, str],
) -> dict[str, EligibilityDecision]:
    """Traduce las decisiones de elegibilidad del request o falla con 422."""

    decisions: dict[str, EligibilityDecision] = {}
    for revision_id, value in raw.items():
        try:
            decisions[revision_id] = EligibilityDecision(value)
        except ValueError as error:
            raise http_error(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="INVALID_ELIGIBILITY_DECISION",
                message=f"unknown eligibility decision {value!r}",
            ) from error
    return decisions


# --------------------------------------------------------------------------- #
# Proyectos                                                                    #
# --------------------------------------------------------------------------- #


@router.get("/projects", response_model=PaginatedProjectsSchema)
def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    services: RagPlatformServices = Depends(get_platform_services),
) -> dict:
    items = [project_to_schema(p) for p in services.list_projects.execute()]
    return paginate(items, page=page, page_size=page_size)


@router.post(
    "/projects",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectSchema,
)
def create_project(
    payload: CreateProjectRequestSchema,
    services: RagPlatformServices = Depends(get_platform_services),
    actor: PlatformActor = Depends(get_actor),
) -> ProjectSchema:
    # El DTO HTTP no expone ``target_bindings`` (target físico): se provisionan
    # server-side, así que la petición de aplicación se arma con bindings vacíos.
    request = CreateProjectRequest(
        project_slug=payload.project_slug,
        display_name=payload.display_name,
        document_type_template=payload.document_type_template,
        corpus_organization_policy=payload.corpus_organization_policy,
        embedding_profiles=payload.embedding_profiles,
    )
    project = services.create_project.execute(request, actor=actor)
    return project_to_schema(project)


@router.get("/projects/{project_id}", response_model=ProjectSchema)
def get_project(
    project_id: str,
    services: RagPlatformServices = Depends(get_platform_services),
) -> ProjectSchema:
    project = services.get_project.execute(_parse_id(IdentityKind.PROJECT, project_id))
    return project_to_schema(project)


@router.patch("/projects/{project_id}", response_model=ProjectSchema)
def update_project(
    project_id: str,
    payload: UpdateProjectRequestSchema,
    services: RagPlatformServices = Depends(get_platform_services),
    actor: PlatformActor = Depends(get_actor),
) -> ProjectSchema:
    project = services.update_project_metadata.execute(
        _parse_id(IdentityKind.PROJECT, project_id),
        display_name=payload.display_name,
        actor=actor,
    )
    return project_to_schema(project)


@router.get(
    "/projects/{project_id}/configuration",
    response_model=ProjectConfigurationSchema,
)
def get_project_configuration(
    project_id: str,
    services: RagPlatformServices = Depends(get_platform_services),
) -> ProjectConfigurationSchema:
    configuration = services.get_project_configuration.execute(
        _parse_id(IdentityKind.PROJECT, project_id)
    )
    return configuration_to_schema(configuration)


@router.patch(
    "/projects/{project_id}/configuration",
    response_model=ProjectConfigurationSchema,
)
def update_project_configuration(
    project_id: str,
    payload: UpdateProjectConfigurationRequestSchema,
    services: RagPlatformServices = Depends(get_platform_services),
    actor: PlatformActor = Depends(get_actor),
) -> ProjectConfigurationSchema:
    # ``target_bindings`` no cruza HTTP (no expone el target físico); el versionado
    # de bindings es server-side, así que la petición se arma con bindings vacíos.
    request = UpdateProjectConfigurationRequest(
        corpus_organization_policy=payload.corpus_organization_policy,
        document_types=payload.document_types,
        embedding_profiles=payload.embedding_profiles,
    )
    configuration = services.create_project_configuration_version.execute(
        _parse_id(IdentityKind.PROJECT, project_id),
        request=request,
        actor=actor,
    )
    return configuration_to_schema(configuration)


# --------------------------------------------------------------------------- #
# Variantes                                                                    #
# --------------------------------------------------------------------------- #


@router.get(
    "/projects/{project_id}/variant-matrix",
    response_model=list[VariantMatrixCellSchema],
)
def get_variant_matrix(
    project_id: str,
    services: RagPlatformServices = Depends(get_platform_services),
) -> list[VariantMatrixCellSchema]:
    cells = services.get_variant_matrix.execute(
        project_id=_parse_id(IdentityKind.PROJECT, project_id)
    )
    return [matrix_cell_to_schema(cell) for cell in cells]


@router.get(
    "/projects/{project_id}/variants",
    response_model=PaginatedVariantsSchema,
)
def list_variants(
    project_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    services: RagPlatformServices = Depends(get_platform_services),
) -> dict:
    variants = services.list_project_variants.execute(
        _parse_id(IdentityKind.PROJECT, project_id)
    )
    items = [variant_to_schema(v) for v in variants]
    return paginate(items, page=page, page_size=page_size)


@router.post(
    "/projects/{project_id}/variants",
    status_code=status.HTTP_201_CREATED,
    response_model=VariantSchema,
)
def create_variant(
    project_id: str,
    payload: CreateVariantRequestSchema,
    services: RagPlatformServices = Depends(get_platform_services),
    actor: PlatformActor = Depends(get_actor),
) -> VariantSchema:
    variant = services.create_variant_from_matrix_cell.execute(
        project_id=_parse_id(IdentityKind.PROJECT, project_id),
        cell_id=payload.cell_id,
        variant_slug=payload.variant_slug,
        actor=actor,
    )
    return variant_to_schema(variant)


# --------------------------------------------------------------------------- #
# Corpus snapshots                                                             #
# --------------------------------------------------------------------------- #


@router.post(
    "/corpus-snapshots",
    status_code=status.HTTP_201_CREATED,
    response_model=CorpusSnapshotSchema,
)
def create_corpus_snapshot(
    payload: CreateCorpusSnapshotRequestSchema,
    services: RagPlatformServices = Depends(get_platform_services),
    actor: PlatformActor = Depends(get_actor),
) -> CorpusSnapshotSchema:
    # Contrato externo canónico: el cliente envía el ``project_id`` completo
    # (``proj_...``). Se valida como ``PlatformId`` (422 fail-closed) y se pasa el
    # cuerpo/slug al caso de uso, que reañade el prefijo. Evita el doble prefijo
    # (``proj_proj_...``) que un body con slug crudo produciría.
    project_pid = _parse_id(IdentityKind.PROJECT, payload.project_id)
    snapshot = services.create_corpus_snapshot.execute(
        project_id=platform_id_body(project_pid),
        document_revision_ids=payload.document_revision_ids,
        actor=actor,
        eligibility_decisions=_eligibility_decisions(payload.eligibility_decisions),
    )
    return snapshot_to_schema(snapshot)


# --------------------------------------------------------------------------- #
# Releases                                                                     #
# --------------------------------------------------------------------------- #


@router.post(
    "/releases",
    status_code=status.HTTP_201_CREATED,
    response_model=ReleaseSchema,
)
def create_release_draft(
    payload: CreateReleaseDraftRequestSchema,
    services: RagPlatformServices = Depends(get_platform_services),
    actor: PlatformActor = Depends(get_actor),
) -> ReleaseSchema:
    release = services.create_release_draft.execute(
        rag_variant_id=_parse_id(IdentityKind.RAG_VARIANT, payload.rag_variant_id),
        corpus_snapshot_id=_parse_id(
            IdentityKind.CORPUS_SNAPSHOT, payload.corpus_snapshot_id
        ),
        target_binding_key=payload.target_binding_key,
        actor=actor,
    )
    return release_to_schema(release)


@router.get("/releases/{rag_release_id}", response_model=ReleaseSchema)
def get_release(
    rag_release_id: str,
    services: RagPlatformServices = Depends(get_platform_services),
) -> ReleaseSchema:
    release = services.get_release.execute(
        _parse_id(IdentityKind.RAG_RELEASE, rag_release_id)
    )
    return release_to_schema(release)


def _run_idempotent(
    *,
    store: IdempotencyStore,
    idempotency_key: str,
    action: str,
    release_id: PlatformId,
    actor: PlatformActor,
    operation,
    request_fields: dict[str, str] | None = None,
) -> dict:
    """Ejecuta un comando de release una sola vez por clave/fingerprint.

    Centraliza la guarda de idempotencia de los cuatro comandos (build/validate/
    publish/retire) para no duplicar el cableado. El fingerprint es ``actor +
    action + rag_release_id`` más ``request_fields`` administrativos que cambian la
    semántica (p. ej. ``reason`` en ``retire``); nunca contenido sensible. Un
    replay de un intento previo **fallido** no devuelve un 200 vacío enmascarando
    el error; se surface con un código estable pidiendo una clave nueva.
    """

    result = IdempotencyGuard(store=store).run(
        idempotency_key=idempotency_key,
        action=action,
        resource_id=release_id.value,
        actor_id=actor.actor_id,
        response_status=status.HTTP_200_OK,
        operation=operation,
        request_fields=request_fields,
    )
    if result.replayed and result.response_status >= 400:
        raise http_error(
            status_code=result.response_status,
            code="IDEMPOTENT_OPERATION_FAILED",
            message=(
                f"a previous {action} attempt for this Idempotency-Key failed; "
                "retry with a new Idempotency-Key"
            ),
        )
    return result.result_json


@router.post(
    "/releases/{rag_release_id}/build",
    response_model=ReleaseBuildReportSchema,
)
def build_release(
    rag_release_id: str,
    idempotency_key: IdempotencyKey,
    services: RagPlatformServices = Depends(get_platform_services),
    actor: PlatformActor = Depends(get_actor),
    store: IdempotencyStore = Depends(get_idempotency_store),
) -> dict:
    release_id = _parse_id(IdentityKind.RAG_RELEASE, rag_release_id)

    def _operation() -> dict:
        report = services.build_release.execute(
            rag_release_id=release_id, actor=actor
        )
        return build_report_to_schema(report).model_dump(mode="json")

    return _run_idempotent(
        store=store,
        idempotency_key=idempotency_key,
        action="build",
        release_id=release_id,
        actor=actor,
        operation=_operation,
    )


@router.post(
    "/releases/{rag_release_id}/validate",
    response_model=ReleaseSchema,
)
def validate_release(
    rag_release_id: str,
    idempotency_key: IdempotencyKey,
    services: RagPlatformServices = Depends(get_platform_services),
    actor: PlatformActor = Depends(get_actor),
    store: IdempotencyStore = Depends(get_idempotency_store),
) -> dict:
    release_id = _parse_id(IdentityKind.RAG_RELEASE, rag_release_id)

    def _operation() -> dict:
        release = services.validate_release.execute(
            rag_release_id=release_id, actor=actor
        )
        return release_to_schema(release).model_dump(mode="json")

    return _run_idempotent(
        store=store,
        idempotency_key=idempotency_key,
        action="validate",
        release_id=release_id,
        actor=actor,
        operation=_operation,
    )


@router.post(
    "/releases/{rag_release_id}/publish",
    response_model=ReleaseSchema,
)
def publish_release(
    rag_release_id: str,
    idempotency_key: IdempotencyKey,
    services: RagPlatformServices = Depends(get_platform_services),
    actor: PlatformActor = Depends(get_actor),
    store: IdempotencyStore = Depends(get_idempotency_store),
) -> dict:
    release_id = _parse_id(IdentityKind.RAG_RELEASE, rag_release_id)

    def _operation() -> dict:
        release = services.publish_release.execute(
            rag_release_id=release_id, actor=actor
        )
        return release_to_schema(release).model_dump(mode="json")

    return _run_idempotent(
        store=store,
        idempotency_key=idempotency_key,
        action="publish",
        release_id=release_id,
        actor=actor,
        operation=_operation,
    )


@router.post(
    "/releases/{rag_release_id}/retire",
    response_model=ReleaseSchema,
)
def retire_release(
    rag_release_id: str,
    payload: RetireReleaseRequestSchema,
    idempotency_key: IdempotencyKey,
    services: RagPlatformServices = Depends(get_platform_services),
    actor: PlatformActor = Depends(get_actor),
    store: IdempotencyStore = Depends(get_idempotency_store),
) -> dict:
    release_id = _parse_id(IdentityKind.RAG_RELEASE, rag_release_id)

    def _operation() -> dict:
        release = services.retire_release.execute(
            rag_release_id=release_id, actor=actor, reason=payload.reason
        )
        return release_to_schema(release).model_dump(mode="json")

    return _run_idempotent(
        store=store,
        idempotency_key=idempotency_key,
        action="retire",
        release_id=release_id,
        actor=actor,
        operation=_operation,
        # ``reason`` es material para retire: misma clave con reason distinto es
        # otra petición lógica (fail-closed, no replay).
        request_fields={"reason": payload.reason},
    )
