import re
import time
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from pydantic import BaseModel

from app.core.diff import diff_graphs
from app.core.graph import Graph, build_graph
from app.core.impact import find_impacts
from app.core.limits import Limits
from app.core.models import Change, ChangeType, Impact
from app.core.parsers.markdown import parse_markdown
from app.core.parsers.openapi import parse_openapi
from app.errors import InputTooLarge, LimitExceeded, UnsupportedInput

_MARKDOWN = {".md", ".markdown", ".txt"}
_OPENAPI = {".yaml", ".yml", ".json"}


@dataclass
class AnalysisResult:
    changes: list[Change]
    impacts: dict[str, list[Impact]]
    graph_a: Graph
    graph_b: Graph
    unsupported: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, float] = field(default_factory=dict)


class QuestionAnswer(BaseModel):
    status: str
    matched: list[str]
    impacts: list[Impact]
    reason: str


def analyze(
    files_a: dict[str, str],
    files_b: dict[str, str],
    limits: Limits | None = None,
    max_depth: int = 3,
) -> AnalysisResult:
    limits = limits or Limits()
    started = time.perf_counter()
    graph_a, unsupported_a = _build(files_a, limits)
    graph_b, unsupported_b = _build(files_b, limits)
    changes = diff_graphs(graph_a, graph_b)
    impacts = {
        c.key: find_impacts(c, graph_a.edges, graph_b.edges, max_depth=max_depth)
        for c in changes
        if c.change_type in (ChangeType.MODIFIED, ChangeType.REMOVED)
    }
    return AnalysisResult(
        changes=changes,
        impacts=impacts,
        graph_a=graph_a,
        graph_b=graph_b,
        unsupported=sorted(set(unsupported_a + unsupported_b)),
        warnings=sorted(set(graph_a.warnings + graph_b.warnings)),
        stats={
            "files_a": len(files_a),
            "files_b": len(files_b),
            "entities_a": len(graph_a.entities),
            "entities_b": len(graph_b.entities),
            "edges_a": len(graph_a.edges),
            "edges_b": len(graph_b.edges),
            "changes": len(changes),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        },
    )


def _build(files: dict[str, str], limits: Limits) -> tuple[Graph, list[str]]:
    if len(files) > limits.max_files:
        raise LimitExceeded(f"too many files (max {limits.max_files})")
    total = 0
    for name, text in files.items():
        _check_name(name)
        size = len(text.encode("utf-8"))
        if size > limits.max_file_bytes:
            raise InputTooLarge(f"{name} exceeds {limits.max_file_bytes} bytes")
        total += size
    if total > limits.max_total_bytes:
        raise InputTooLarge(f"input exceeds {limits.max_total_bytes} bytes")

    results, unsupported = [], []
    for name in sorted(files):
        ext = PurePosixPath(name).suffix.lower()
        if ext in _MARKDOWN:
            results.append(parse_markdown(name, files[name], limits))
        elif ext in _OPENAPI:
            try:
                results.append(parse_openapi(name, files[name], limits))
            except UnsupportedInput as exc:
                unsupported.append(exc.message)
        else:
            unsupported.append(f"{name}: unsupported file type")
    return build_graph(results), unsupported


def _check_name(name: str) -> None:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", name) or not name:
        raise UnsupportedInput(f"unsafe file path: {name!r}")


def answer_question(result: AnalysisResult, question: str) -> QuestionAnswer:
    entities = {**result.graph_a.entities, **result.graph_b.entities}
    matched = sorted(
        key
        for key, e in entities.items()
        if re.search(rf"(?<![\w/]){re.escape(e.name)}(?![\w/])", question)
    )
    if not matched:
        return QuestionAnswer(
            status="uncertain",
            matched=[],
            impacts=[],
            reason="The question does not name any known endpoint, schema, section or requirement.",
        )
    changed = [k for k in matched if k in result.impacts]
    if not changed:
        return QuestionAnswer(
            status="no_change",
            matched=matched,
            impacts=[],
            reason="The named entities did not change between the two versions.",
        )
    return QuestionAnswer(
        status="answered",
        matched=changed,
        impacts=[i for k in changed for i in result.impacts[k]],
        reason="Impacts are listed with evidence paths; inferred impacts are labeled as such.",
    )
