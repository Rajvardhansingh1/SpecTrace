from typing import Annotated

from fastapi import APIRouter, Depends, Request
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


def _summary(row: RunRow) -> dict:
    return {
        "id": row.id,
        "status": row.status,
        "label_a": row.label_a,
        "label_b": row.label_b,
        "created_at": row.created_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
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
