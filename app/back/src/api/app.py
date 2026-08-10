"""FastAPI application exposing Chunking, Embedding, Indexing and Retrieval.

Every domain shares one error envelope so the frontend needs a single handler.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.dependencies import PipelineServices
from embedding.api.router import router as embedding_router
from indexing.api.router import router as indexing_router
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

    app = FastAPI(title="Chatbot SST Pipeline API", version="0.1.0", lifespan=lifespan)
    app.state.feature_flags = services.feature_flags
    app.state.consumer_scope = services.consumer_scope
    app.state.embedding_read_service = services.embedding_read_service
    app.state.embedding_create_run = services.embedding_create_run
    app.state.embedding_executor = services.embedding_executor
    app.state.indexing_read_service = services.indexing_read_service
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

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
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
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
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

    app.include_router(embedding_router)
    app.include_router(indexing_router)
    app.include_router(retrieval_router)
    return app
