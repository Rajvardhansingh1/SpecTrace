from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.adapters.store import RunStore, init_schema, make_engine
from app.api.ratelimit import SlidingWindowLimiter
from app.api.v1.runs import router as runs_router
from app.config import Settings
from app.errors import SpecTraceError

# Never limited, so platform health checks keep working while a client is throttled.
_UNLIMITED_PATHS = {"/health"}


def _envelope(status: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


def _client_key(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.split(",")[-1].strip()
        if last:
            return last
    return request.client.host if request.client else "unknown"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="SpecTrace", version=__version__)

    @app.exception_handler(SpecTraceError)
    async def handle_spectrace_error(_: Request, exc: SpecTraceError):
        return _envelope(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_invalid_request(_: Request, exc: RequestValidationError):
        # Pydantic details can echo submitted input, so only a fixed message is returned.
        return _envelope(422, "invalid_request", "request body is invalid")

    general_limiter = SlidingWindowLimiter(settings.rate_limit_per_minute)
    heavy_limiter = SlidingWindowLimiter(settings.rate_limit_heavy_per_minute)
    app.state.limiters = (general_limiter, heavy_limiter)

    # Middleware added later runs earlier: the rate limit is checked before the size check.
    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > settings.max_request_bytes:
            return _envelope(413, "input_too_large", "request body too large")
        return await call_next(request)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.url.path in _UNLIMITED_PATHS or request.method == "OPTIONS":
            return await call_next(request)
        # POSTs run the analysis, which is the expensive operation, so they get the tight bucket.
        limiter = heavy_limiter if request.method == "POST" else general_limiter
        allowed, retry_after = limiter.check(_client_key(request, settings.trust_proxy_headers))
        if not allowed:
            return _envelope(
                429,
                "rate_limited",
                "too many requests",
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

    # Added last so it is outermost: CORS headers are also set on 413 and 429 responses.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["Retry-After"],
    )

    engine = make_engine(settings.database_url)
    init_schema(engine)
    app.state.store = RunStore(engine)
    app.include_router(runs_router)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
