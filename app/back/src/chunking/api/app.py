from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from chunking.api.dependencies import build_run_service, build_run_service_from_env
from chunking.api.router import router


def create_app(
    *,
    docs_normalized: Path,
    chunks_root: Path,
    connection: object | None = None,
) -> FastAPI:
    service = (
        build_run_service(
            docs_normalized=docs_normalized,
            chunks_root=chunks_root,
            connection=connection,
        )
        if connection is not None
        else build_run_service_from_env(
            docs_normalized=docs_normalized,
            chunks_root=chunks_root,
        )
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            service.close()

    app = FastAPI(title="Chunking API", version="0.1.0", lifespan=lifespan)
    app.state.chunking_run_service = service

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

    @app.exception_handler(HTTPException)
    async def chunking_http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return _error_response(
            status_code=exc.status_code,
            code="CHUNKING_HTTP_EXCEPTION",
            message=str(exc.detail),
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(
        _request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        code = "CHUNKING_ROUTE_NOT_FOUND" if exc.status_code == 404 else "CHUNKING_HTTP_EXCEPTION"
        return _error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        _request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            status_code=422,
            code="CHUNKING_INVALID_REQUEST",
            message="request validation failed",
            details={"issues": exc.errors()},
        )

    app.include_router(router)
    return app
