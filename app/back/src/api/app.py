"""FastAPI application exposing Chunking, Embedding, Indexing and Retrieval.

Every domain shares one error envelope so the frontend needs a single handler.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.dependencies import PipelineServices, require_authenticated_principal
from embedding.api.router import router as embedding_router
from indexing.api.router import router as indexing_router
from rag_platform.api.router import router as platform_router
from rag_platform.domain.errors import RagPlatformError
from rag_platform.domain.identity import InvalidIdentity
from retrieval.api.router import router as retrieval_router


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "run_id": None,
                "details": details or {},
            }
        },
    )


def create_app(*, services: PipelineServices) -> FastAPI:
    """Build the bundle-first HTTP application around already-wired services."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        services.indexing_reconciler.reconcile()
        services.embedding_executor.reconcile()
        try:
            yield
        finally:
            services.close()

    app = FastAPI(
        title="Chatbot SST Pipeline API",
        version="0.1.0",
        lifespan=lifespan,
        dependencies=[Depends(require_authenticated_principal)],
    )
    app.state.feature_flags = services.feature_flags
    app.state.consumer_scope = services.consumer_scope
    app.state.embedding_read_service = services.embedding_read_service
    app.state.chunk_bundles = services.chunk_bundles
    app.state.embedding_runs = services.embedding_runs
    app.state.embedding_bundles = services.embedding_bundles
    app.state.embedding_create_run = services.embedding_create_run
    app.state.embedding_executor = services.embedding_executor
    app.state.indexing_read_service = services.indexing_read_service
    app.state.indexing_runs = services.indexing_runs
    app.state.indexing_create_run = services.indexing_create_run
    app.state.indexing_executor = services.indexing_executor
    app.state.indexing_activate = services.indexing_activate
    app.state.indexing_rollback = services.indexing_rollback
    app.state.retrieval_profiles = services.retrieval_profiles
    app.state.retrieval_create_profile = services.retrieval_create_profile
    app.state.retrieval_activate_profile = services.retrieval_activate_profile
    app.state.retrieval_profile_status = services.retrieval_profile_status
    app.state.retrieval_validate = services.retrieval_validate
    app.state.retrieval_search = services.retrieval_search
    app.state.http_authenticator = services.http_authenticator
    # Fase 7: superficie administrativa de plataforma. ``None`` cuando el flag
    # ``rag_platform_v1`` está apagado; el router hace 503 fail-closed vía su gate.
    app.state.rag_platform = services.rag_platform
    app.state.platform_idempotency_store = services.platform_idempotency_store

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
                headers=exc.headers,
            )
        return _error_response(
            status_code=exc.status_code,
            code="PIPELINE_HTTP_EXCEPTION",
            message=str(exc.detail),
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_exception_handler(
        _request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
                headers=exc.headers,
            )
        code = "PIPELINE_ROUTE_NOT_FOUND" if exc.status_code == 404 else "PIPELINE_HTTP_EXCEPTION"
        return _error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            status_code=422,
            code="PIPELINE_INVALID_REQUEST",
            message="request validation failed",
            details={"issues": exc.errors()},
        )

    @app.exception_handler(RagPlatformError)
    async def rag_platform_error_handler(
        _request,
        exc: RagPlatformError,
    ) -> JSONResponse:
        # Traducción centralizada única: el ``code``/``http_status`` estable del
        # error de dominio se mapea al envelope compartido. Sin taxonomía nueva ni
        # ``try/except`` duplicado por endpoint.
        return _error_response(
            status_code=exc.http_status,
            code=exc.code,
            message=str(exc),
        )

    @app.exception_handler(InvalidIdentity)
    async def invalid_identity_handler(
        _request,
        exc: InvalidIdentity,
    ) -> JSONResponse:
        # Un ``slug``/ID de plataforma malformado (en path o en body) construye un
        # ``PlatformId`` inválido dentro del caso de uso: se traduce a 422 estable
        # en vez de escapar como 500. Fail-closed.
        return _error_response(
            status_code=422,
            code="INVALID_PLATFORM_ID",
            message=str(exc),
        )

    app.include_router(embedding_router)
    app.include_router(indexing_router)
    app.include_router(retrieval_router)
    app.include_router(platform_router)
    return app
