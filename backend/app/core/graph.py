import re
from dataclasses import dataclass, field

from app.core.models import (
    Edge,
    Entity,
    EntityKind,
    Label,
    ParseResult,
    RawRef,
    RawRefKind,
)

_PARAM_RE = re.compile(r"\{[^}]*\}")
NAME_CONFIDENCE = 0.8
PROPERTY_CONFIDENCE = 0.6
PROPERTY_MIN_SHARED = 2
PROPERTY_MIN_JACCARD = 0.75


@dataclass
class Graph:
    entities: dict[str, Entity]
    edges: list[Edge]
    warnings: list[str] = field(default_factory=list)


def _norm_path(path: str) -> str:
    return _PARAM_RE.sub("{}", path.rstrip("/") or "/")


def _rank(edge: Edge) -> tuple[bool, float]:
    return (edge.label is Label.CONFIRMED, edge.confidence)


def build_graph(results: list[ParseResult]) -> Graph:
    entities: dict[str, Entity] = {}
    warnings: list[str] = []
    for r in results:
        warnings.extend(r.warnings)
        for e in r.entities:
            if e.key in entities:
                warnings.append(f"duplicate entity {e.key}; keeping the first")
                continue
            entities[e.key] = e

    schema_keys = {e.name: e.key for e in entities.values() if e.kind is EntityKind.SCHEMA}
    schema_props = {
        e.key: set(e.attrs.get("properties", {}))
        for e in entities.values()
        if e.kind is EntityKind.SCHEMA
    }
    endpoints = {}
    for e in entities.values():
        if e.kind is EntityKind.ENDPOINT:
            method, path = e.name.split(" ", 1)
            endpoints[(method, _norm_path(path))] = e.key

    candidates: list[Edge] = []
    for r in results:
        for edge in r.edges:
            if edge.source_key in entities and edge.target_key in entities:
                candidates.append(edge)
            else:
                warnings.append(f"unresolved reference {edge.source_key} -> {edge.target_key}")
        for ref in r.raw_refs:
            if ref.source_key not in entities:
                continue
            candidates.extend(
                _resolve(ref, entities, schema_keys, schema_props, endpoints, warnings)
            )

    merged: dict[tuple[str, str, str], Edge] = {}
    for e in candidates:
        if e.source_key == e.target_key:
            continue
        k = (e.source_key, e.target_key, e.relation)
        if k not in merged or _rank(e) > _rank(merged[k]):
            merged[k] = e
    return Graph(entities=entities, edges=list(merged.values()), warnings=warnings)


def _edge(ref: RawRef, target: str, relation: str, label: Label, conf: float, reason: str) -> Edge:
    return Edge(
        source_key=ref.source_key,
        target_key=target,
        relation=relation,
        label=label,
        confidence=conf,
        evidence=ref.location,
        reason=reason,
    )


def _where(ref: RawRef) -> str:
    return f"{ref.location.file}:{ref.location.line_start}"


def _resolve(ref, entities, schema_keys, schema_props, endpoints, warnings) -> list[Edge]:
    if ref.kind is RawRefKind.ENDPOINT:
        method, path = ref.value.split(" ", 1)
        target = endpoints.get((method, _norm_path(path)))
        if target is None:
            warnings.append(f"{_where(ref)}: unknown endpoint {ref.value}")
            return []
        return [
            _edge(ref, target, "mentions_endpoint", Label.CONFIRMED, 1.0, f"mentions {ref.value}")
        ]

    if ref.kind is RawRefKind.ANCHOR:
        source_file = entities[ref.source_key].location.file
        target = f"section:{source_file}#{ref.value}"
        if target not in entities:
            warnings.append(f"{_where(ref)}: unresolved anchor #{ref.value}")
            return []
        return [_edge(ref, target, "links_to", Label.CONFIRMED, 1.0, f"link to #{ref.value}")]

    if ref.kind is RawRefKind.REQUIREMENT:
        target = f"requirement:{ref.value}"
        if target not in entities:
            warnings.append(f"{_where(ref)}: unknown requirement {ref.value}")
            return []
        return [
            _edge(
                ref, target, "mentions_requirement", Label.CONFIRMED, 1.0, f"mentions {ref.value}"
            )
        ]

    if ref.kind is RawRefKind.IDENTIFIER:
        target = schema_keys.get(ref.value)
        if target is None:
            return []
        return [
            _edge(
                ref,
                target,
                "mentions_name",
                Label.INFERRED,
                NAME_CONFIDENCE,
                f"backticked identifier `{ref.value}` equals a schema name",
            )
        ]

    if ref.kind is RawRefKind.JSON_KEYS:
        keys = set(ref.value.split(","))
        edges = []
        for target, props in schema_props.items():
            shared = keys & props
            union = keys | props
            if (
                len(shared) >= PROPERTY_MIN_SHARED
                and len(shared) / len(union) >= PROPERTY_MIN_JACCARD
            ):
                edges.append(
                    _edge(
                        ref,
                        target,
                        "similar_properties",
                        Label.INFERRED,
                        PROPERTY_CONFIDENCE,
                        f"example keys {sorted(shared)} overlap schema properties",
                    )
                )
        return edges
    return []
