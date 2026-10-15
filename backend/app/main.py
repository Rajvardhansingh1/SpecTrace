from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.adapters.store import RunStore, init_schema, make_engine
from app.api.v1.runs import router as runs_router
from app.config import Settings
from app.errors import SpecTraceError


def _envelope(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="SpecTrace", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(SpecTraceError)
    async def handle_spectrace_error(_: Request, exc: SpecTraceError):
        return _envelope(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_invalid_request(_: Request, exc: RequestValidationError):
        # Pydantic details can echo submitted input, so only a fixed message is returned.
        return _envelope(422, "invalid_request", "request body is invalid")

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > settings.max_request_bytes:
            return _envelope(413, "input_too_large", "request body too large")
        return await call_next(request)

    engine = make_engine(settings.database_url)
    init_schema(engine)
    app.state.store = RunStore(engine)
    app.include_router(runs_router)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
