import hmac
import logging
import mimetypes
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import router
from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.core.errors import error_body
from app.core.logging import configure_logging, log_event, request_id_var
from app.core.ratelimit import limiter
from app.core.security import token_hash
from app.panel import render_error
from app.panel import router as panel_router
from app.services.recovery import recover_interrupted_research

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("relationships")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
# Strict policy for the panel; Swagger UI loads its own assets from a CDN.
PANEL_CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


@asynccontextmanager
async def lifespan(app):
    problems = settings.production_problems()
    if problems:
        for problem in problems:
            log_event(logger, "config.invalid", logging.CRITICAL, problem=problem)
        raise RuntimeError("Unsafe production configuration: " + " ".join(problems))
    if settings.app_env == "production" and not settings.cookie_secure:
        log_event(logger, "config.warning", logging.WARNING,
                  problem="COOKIE_SECURE=false: serve the panel over HTTPS for network access.")
    # Research left in a running state by the old synchronous demo runner.
    with SessionLocal() as db:
        recovered = recover_interrupted_research(db)
    log_event(logger, "app.started", env=settings.app_env, interrupted_research=recovered)
    yield
    log_event(logger, "app.stopped")


docs_enabled = settings.enable_api_docs
app = FastAPI(
    lifespan=lifespan,
    title="Relationship Intelligence Platform",
    version="1.1.0",
    description=(
        "Research tool with optional login. Integrations may import evidence; people review "
        "and approve candidates. Errors return {detail, code, retryable, request_id}. "
        "POST endpoints that create data accept an Idempotency-Key header."
    ),
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)
app.include_router(router)
app.include_router(panel_router)
# Self-hosted brand fonts; the slim image has no system MIME table entry for woff2.
mimetypes.add_type("font/woff2", ".woff2")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


class BodySizeLimit:
    """Buffers at most MAX_REQUEST_BYTES of a body, including chunked uploads without
    Content-Length, and answers 413 before the application parses anything."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        chunks, size, limit = [], 0, settings.max_request_bytes
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return  # client disconnected before sending the body; nothing to answer
            chunks.append(message.get("body", b""))
            size += len(chunks[-1])
            if size > limit:
                response = JSONResponse(error_body(413, "Request body is too large."), status_code=413)
                return await response(scope, receive, send)
            if not message.get("more_body"):
                break
        body, replayed = b"".join(chunks), False

        async def replay():
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay, send)


# Registered before observe(), so observe wraps it and logs/labels its 413 responses.
app.add_middleware(BodySizeLimit)


def client_key(request):
    """Rate-limit identity: session, integration key, then IP (Docker may hide real IPs)."""
    authorization = request.headers.get("authorization", "")
    key = settings.n8n_api_key
    # Only a valid key shares the integration bucket; junk tokens count against their IP.
    if key and hmac.compare_digest(authorization.encode(), f"Bearer {key}".encode()):
        return "service"
    token = request.cookies.get("rip_session")
    if token:
        return "session:" + token_hash(token)[:24]
    return "ip:" + (request.client.host if request.client else "unknown")


def finalize(request, response, request_id):
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if not request.url.path.startswith(DOCS_PATHS):
        response.headers["Content-Security-Policy"] = PANEL_CSP
    return response


@app.middleware("http")
async def observe(request: Request, call_next):
    supplied = request.headers.get("x-request-id", "")
    request_id = supplied if REQUEST_ID.fullmatch(supplied) else str(uuid4())
    token = request_id_var.set(request_id)
    start = time.monotonic()
    path = request.url.path
    error = None
    try:
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > settings.max_request_bytes):
            response = JSONResponse(error_body(413, "Request body is too large."), status_code=413)
        elif not path.startswith(("/static/", "/health")) and not limiter.allow(
            client_key(request), settings.rate_limit_per_minute
        ):
            response = JSONResponse(
                error_body(429, "Too many requests. Try again in a minute."),
                status_code=429,
                headers={"Retry-After": "60"},
            )
        else:
            try:
                response = await call_next(request)
            except Exception as exc:
                # Full traceback stays in server logs; callers only get the request ID.
                error = type(exc).__name__
                log_event(logger, "http.unhandled_error", logging.ERROR, exc_info=True,
                          action=f"{request.method} {path}")
                response = JSONResponse(
                    error_body(500, "An unexpected error occurred."), status_code=500
                )
        finalize(request, response, request_id)
        log_event(
            logger,
            "http.request",
            logging.WARNING if response.status_code >= 500 else logging.INFO,
            user_id=getattr(request.state, "user_id", None),
            action=f"{request.method} {path}",
            status=response.status_code,
            duration=round(time.monotonic() - start, 4),
            error=error,
        )
        return response
    finally:
        request_id_var.reset(token)


app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[h.strip() for h in settings.allowed_hosts.split(",") if h.strip()] or ["*"],
)
if settings.allowed_origins.strip():
    # Outermost, so 400/413/429/500 responses from inner layers carry CORS headers too.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[x.strip() for x in settings.allowed_origins.split(",") if x.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Idempotency-Key",
                       "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if exc.status_code < 400:  # panel redirects (for example to the login page)
        return Response(status_code=exc.status_code, headers=exc.headers)
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    if request.url.path.startswith("/panel") or request.url.path == "/":
        return render_error(request, exc.status_code, detail)
    return JSONResponse(error_body(exc.status_code, detail), status_code=exc.status_code,
                        headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def invalid_payload(request, exc):
    body = error_body(422, [
        {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
    ])
    if request.url.path.startswith("/panel"):
        return render_error(request, 422, "Geçersiz adres veya parametre.")
    return JSONResponse(status_code=422, content=body)


@app.get("/health", tags=["System"])
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        log_event(logger, "health.database_unavailable", logging.ERROR, exc_info=True)
        return JSONResponse(error_body(503, "Database unavailable."), status_code=503)
    return {"status": "ok"}
