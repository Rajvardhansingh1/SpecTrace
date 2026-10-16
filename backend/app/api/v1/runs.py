from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.adapters.store import RunRow, RunStore
from app.core.pipeline import AnalysisResult, QuestionAnswer, analyze, answer_question
from app.errors import SpecTraceError

router = APIRouter(prefix="/v1")


class RunRequest(BaseModel):
    files_a: dict[str, str] = Field(max_length=200)
    files_b: dict[str, str] = Field(max_length=200)
    label_a: str = Field(default="A", max_length=100)
    label_b: str = Field(default="B", max_length=100)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class NotFound(SpecTraceError):
    code = "not_found"
    status = 404


def get_store(request: Request) -> RunStore:
    return request.app.state.store


Store = Annotated[RunStore, Depends(get_store)]


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


def _load(store: RunStore, run_id: str) -> RunRow:
    row = store.get(run_id)
    if row is None:
        raise NotFound("run not found")
    return row


@router.post("/runs", status_code=201)
def create_run(body: RunRequest, store: Store):
    row = store.create(body.label_a, body.label_b, body.files_a, body.files_b)
    try:
        result = _serialize(analyze(body.files_a, body.files_b))
    except SpecTraceError as exc:
        store.fail(row.id, exc.code)
        raise
    store.finish(row.id, result)
    return {**_summary(store.get(row.id)), "stats": result["stats"]}


@router.get("/runs")
def list_runs(store: Store):
    return {"runs": [_summary(r) for r in store.list()]}


@router.get("/runs/{run_id}")
def get_run(run_id: str, store: Store):
    row = _load(store, run_id)
    return {**_summary(row), "result": row.result}


@router.post("/runs/{run_id}/ask", response_model=QuestionAnswer)
def ask(run_id: str, body: AskRequest, store: Store):
    row = _load(store, run_id)
    if row.status != "done":
        raise NotFound("run has no result")
    # Analysis is deterministic, so re-running on the stored inputs reproduces the graphs.
    return answer_question(analyze(row.files_a, row.files_b), body.question)


MAX_SNIPPET_LINE_CHARS = 400


@router.get("/runs/{run_id}/snippet")
def snippet(
    run_id: str,
    store: Store,
    version: Literal["a", "b"],
    file: Annotated[str, Query(min_length=1, max_length=300)],
    line: Annotated[int, Query(ge=1, le=10_000_000)],
    context: Annotated[int, Query(ge=0, le=10)] = 2,
):
    """Source lines around a cited location, for showing evidence next to an impact."""
    row = _load(store, run_id)
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
