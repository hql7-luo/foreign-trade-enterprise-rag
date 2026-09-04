"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager, nullcontext
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.dependencies import get_rag_service
from app.api.routes import router
from app.auth import get_auth_service
from app.config import get_settings
from app.demo_safety import runtime_lease
from app.observability import configure_logging, count, event, request_id, timing
from app.security.operations import RateLimiter, client_address, operation


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    with runtime_lease(settings) if settings.demo_mode else nullcontext():
        if settings.environment == "production":
            # Initialize the configured embedding/auth services before accepting traffic.
            get_rag_service()
            get_auth_service()
        event("application_started")
        try:
            yield
        finally:
            if get_rag_service.cache_info().currsize:
                get_rag_service().retrieval.vector_store.close()
                get_rag_service.cache_clear()
            get_auth_service.cache_clear()
            event("application_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    limiter = RateLimiter(settings)
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )
    allowed_hosts = [item.strip() for item in settings.allowed_hosts.split(",") if item.strip()]
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    if settings.allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins.split(","),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request, _error):
        # Pydantic errors may echo password/input values; never serialize them publicly.
        return JSONResponse(status_code=422, content={"detail": "Request validation failed"})

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        token = request_id.set(str(uuid4()))
        started = perf_counter()
        category = operation(request.method, request.url.path)
        count("requests_total")
        try:
            if not limiter.allow(client_address(request, settings), category):
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Try again in a minute."},
                    headers={"Retry-After": "60"},
                )
            elif (
                settings.demo_mode
                and settings.public_demo_read_only
                and category
                in {
                    "review",
                    "upload",
                    "ingestion",
                }
            ):
                response = JSONResponse(
                    status_code=403,
                    content={"detail": "Public demo is read-only. Changes require the local demo."},
                )
            elif int(request.headers.get("content-length", "0")) > (
                settings.max_upload_bytes + 16384 if category == "upload" else 65536
            ):
                response = JSONResponse(status_code=413, content={"detail": "Request is too large"})
            else:
                response = await call_next(request)
        except Exception as exc:
            event("unexpected_error", operation=category, error_type=type(exc).__name__)
            response = JSONResponse(
                status_code=503,
                content={"detail": "Service temporarily unavailable. Please retry later."},
            )
        duration = perf_counter() - started
        timing("request", duration)
        if response.status_code >= 400:
            count("errors_total")
        event(
            "login_success"
            if category == "login" and response.status_code == 200
            else "login_failure"
            if category == "login"
            else "request_completed",
            operation=category,
            status=response.status_code,
            duration_ms=round(duration * 1000, 2),
        )
        response.headers["X-Request-ID"] = request_id.get()
        request_id.reset(token)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    application.include_router(router)
    return application


app = create_app()
