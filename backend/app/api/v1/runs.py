import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.adapters.store import RunRow, RunStore, owner_hash
from app.core.models import Impact
from app.core.pipeline import AnalysisResult, analyze
from app.errors import OwnerRequired, SpecTraceError
from app.service import AIService

router = APIRouter(prefix="/v1")

# A random value the browser creates and keeps. Only its hash is stored.
_OWNER_TOKEN = re.compile(r"[A-Za-z0-9_-]{16,128}")


class RunRequest(BaseModel):
    files_a: dict[str, str] = Field(max_length=200)
    files_b: dict[str, str] = Field(max_length=200)
    label_a: str = Field(default="A", max_length=100)
    label_b: str = Field(default="B", max_length=100)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class NarrativeRequest(BaseModel):
    refresh: bool = False


class Citation(BaseModel):
    id: str
    kind: str
    title: str
    text: str
    file: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    version: str | None = None
    via: str | None = None
    similarity: float | None = None


class AskResponse(BaseModel):
    status: str
    matched: list[str]
    impacts: list[Impact]
    reason: str
    # Set only when a language model wrote the answer. It is always checked against the context.
    answer: str | None = None
    citations: list[Citation] = []
    generated: bool = False
    model: str | None = None
    warnings: list[str] = []
    truncated: bool = False
    retrieval: dict[str, Any] | None = None


class NotFound(SpecTraceError):
    code = "not_found"
    status = 404


def get_store(request: Request) -> RunStore:
    return request.app.state.store


def get_service(request: Request) -> AIService:
    return request.app.state.ai_service


def get_owner(request: Request) -> str:
    token = request.headers.get("x-owner-token", "")
    if not _OWNER_TOKEN.fullmatch(token):
        raise OwnerRequired("Send a random X-Owner-Token header of 16 to 128 characters.")
    return owner_hash(token)


Store = Annotated[RunStore, Depends(get_store)]
Service = Annotated[AIService, Depends(get_service)]
Owner = Annotated[str, Depends(get_owner)]


def _iso(moment: datetime) -> str:
    # SQLite returns naive datetimes that were stored as UTC; a browser would read them as local.
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).isoformat()


def _summary(row: RunRow) -> dict:
    return {
        "id": row.id,
        "status": row.status,
        "label_a": row.label_a,
        "label_b": row.label_b,
        "created_at": _iso(row.created_at),
        "finished_at": _iso(row.finished_at) if row.finished_at else None,
        "error_code": row.error_code,
    }


def _serialize(res: AnalysisResult) -> dict:
    entities = {**res.graph_a.entities, **res.graph_b.entities}
    return {
        "changes": [c.model_dump(mode="json") for c in res.changes],
        "impacts": {k: [i.model_dump(mode="json") for i in v] for k, v in res.impacts.items()},
        "graph": {
            "entities": [e.model_dump(mode="json", exclude={"text"}) for e in entities.values()],
            "edges_a": [e.model_dump(mode="json") for e in res.graph_a.edges],
            "edges_b": [e.model_dump(mode="json") for e in res.graph_b.edges],
        },
        "unsupported": res.unsupported,
        "warnings": res.warnings,
        "stats": res.stats,
    }


def _load(store: RunStore, run_id: str, owner: str) -> RunRow:
    # A run that belongs to someone else is reported as missing, so its existence is not revealed.
    row = store.get(run_id, owner)
    if row is None:
        raise NotFound("run not found")
    return row


@router.get("/capabilities")
def capabilities(service: Service):
    """What the server can do, and who would receive document text. No secrets."""
    return service.capabilities()


@router.post("/runs", status_code=201)
def create_run(body: RunRequest, store: Store, owner: Owner):
    row = store.create(body.label_a, body.label_b, body.files_a, body.files_b, owner)
    try:
        result = _serialize(analyze(body.files_a, body.files_b))
    except SpecTraceError as exc:
        store.fail(row.id, exc.code)
        raise
    store.finish(row.id, result)
    return {**_summary(store.get(row.id)), "stats": result["stats"]}


@router.get("/runs")
def list_runs(store: Store, owner: Owner):
    return {"runs": [_summary(r) for r in store.list(owner=owner)]}


@router.get("/runs/{run_id}")
def get_run(run_id: str, store: Store, owner: Owner):
    row = _load(store, run_id, owner)
    return {**_summary(row), "result": row.result}


@router.post("/runs/{run_id}/narrative")
def narrative(run_id: str, body: NarrativeRequest, store: Store, service: Service, owner: Owner):
    """Summaries of both versions and of what changed, written by the language model."""
    row = _load(store, run_id, owner)
    if row.status != "done":
        raise NotFound("run has no result")
    return service.narrative(row, owner, refresh=body.refresh)


@router.post("/runs/{run_id}/ask", response_model=AskResponse)
def ask(run_id: str, body: AskRequest, store: Store, service: Service, owner: Owner):
    row = _load(store, run_id, owner)
    if row.status != "done":
        raise NotFound("run has no result")
    return service.ask(row, owner, body.question)


MAX_SNIPPET_LINE_CHARS = 400


@router.get("/runs/{run_id}/snippet")
def snippet(
    run_id: str,
    store: Store,
    owner: Owner,
    version: Literal["a", "b"],
    file: Annotated[str, Query(min_length=1, max_length=300)],
    line: Annotated[int, Query(ge=1, le=10_000_000)],
    context: Annotated[int, Query(ge=0, le=10)] = 2,
):
    """Source lines around a cited location, for showing evidence next to an impact."""
    row = _load(store, run_id, owner)
    files = row.files_a if version == "a" else row.files_b
    # A dictionary lookup on the stored names, never a filesystem path.
    text = files.get(file)
    if text is None:
        raise NotFound("file not found in this run")
    lines = text.splitlines()
    if line > len(lines):
        raise NotFound("line is outside the file")
    first, last = max(1, line - context), min(len(lines), line + context)
    return {
        "file": file,
        "version": version,
        "line": line,
        "lines": [
            {"n": n, "text": lines[n - 1][:MAX_SNIPPET_LINE_CHARS]} for n in range(first, last + 1)
        ],
    }
