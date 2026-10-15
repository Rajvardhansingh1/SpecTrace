import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from app.core.limits import Limits
from app.core.models import Edge, Entity, EntityKind, Label, Location, ParseResult
from app.errors import LimitExceeded, ParseError, UnsupportedInput

REF_RE = re.compile(r"^#/components/schemas/([A-Za-z0-9_.\-]+)$")
METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


def parse_openapi(file: str, text: str, limits: Limits) -> ParseResult:
    doc = _load(file, text, limits)
    if not isinstance(doc, Mapping) or not ("openapi" in doc or "swagger" in doc):
        raise UnsupportedInput(f"{file}: not an OpenAPI document")

    lines = text.splitlines()
    top = _spans(doc, max(len(lines), 1), lines)
    result = ParseResult()

    paths = doc.get("paths")
    if isinstance(paths, Mapping) and "paths" in top:
        path_spans = _spans(paths, top["paths"][1], lines)
        for path, item in paths.items():
            if not isinstance(item, Mapping):
                continue
            op_spans = _spans(item, path_spans[path][1], lines)
            shared = _plain(item.get("parameters") or [])
            for method in METHODS:
                op = item.get(method)
                if not isinstance(op, Mapping):
                    continue
                key = f"endpoint:{method.upper()} {path}"
                start, end = op_spans[method]
                result.entities.append(
                    _entity(
                        key,
                        EntityKind.ENDPOINT,
                        f"{method.upper()} {path}",
                        file,
                        lines,
                        start,
                        end,
                        op,
                        _endpoint_attrs(op, shared),
                    )
                )
                result.edges.extend(_ref_edges(key, op, file))

    components = doc.get("components")
    if isinstance(components, Mapping) and "components" in top:
        comp_spans = _spans(components, top["components"][1], lines)
        schemas = components.get("schemas")
        if isinstance(schemas, Mapping) and "schemas" in comp_spans:
            schema_spans = _spans(schemas, comp_spans["schemas"][1], lines)
            for name, schema in schemas.items():
                if not isinstance(schema, Mapping):
                    continue
                key = f"schema:{name}"
                start, end = schema_spans[name]
                result.entities.append(
                    _entity(
                        key,
                        EntityKind.SCHEMA,
                        str(name),
                        file,
                        lines,
                        start,
                        end,
                        schema,
                        _schema_attrs(schema),
                    )
                )
                result.edges.extend(e for e in _ref_edges(key, schema, file) if e.target_key != key)

    if len(result.entities) > limits.max_entities:
        raise LimitExceeded(f"{file}: too many entities")
    return result


def _load(file: str, text: str, limits: Limits) -> Any:
    try:
        doc = YAML(typ="rt").load(text)
    except YAMLError as exc:
        raise ParseError(f"{file}: invalid YAML or JSON") from exc
    except RecursionError as exc:
        # ruamel's composer recurses; extreme nesting must map to a 4xx, not a 500.
        raise LimitExceeded(f"{file}: document is nested too deeply") from exc
    _check_bounds(doc, limits.max_yaml_nodes, limits.max_yaml_depth)
    return doc


def _check_bounds(root: Any, max_nodes: int, max_depth: int) -> None:
    """Iterative walk without a visited set, so alias expansion is counted and capped."""
    count = 0
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > max_nodes:
            raise LimitExceeded("document has too many nodes")
        if depth > max_depth:
            raise LimitExceeded("document is nested too deeply")
        if isinstance(node, Mapping):
            stack.extend((v, depth + 1) for v in node.values())
        elif isinstance(node, list):
            stack.extend((v, depth + 1) for v in node)


def _spans(mapping: Any, parent_end: int, lines: list[str]) -> dict[Any, tuple[int, int]]:
    keys = list(mapping.keys())
    starts = [mapping.lc.key(k)[0] + 1 for k in keys]
    spans = {}
    for i, key in enumerate(keys):
        end = starts[i + 1] - 1 if i + 1 < len(keys) else parent_end
        end = max(end, starts[i])
        while end > starts[i] and end <= len(lines) and not lines[end - 1].strip():
            end -= 1
        spans[key] = (starts[i], end)
    return spans


def _plain(node: Any) -> Any:
    if isinstance(node, Mapping):
        return {str(k): _plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_plain(v) for v in node]
    return node


def _hash(plain: Any) -> str:
    return hashlib.sha256(json.dumps(plain, sort_keys=True, default=str).encode()).hexdigest()


def _entity(key, kind, name, file, lines, start, end, node, attrs) -> Entity:
    return Entity(
        key=key,
        kind=kind,
        name=name,
        location=Location(file=file, line_start=start, line_end=end),
        content_hash=_hash(_plain(node)),
        text="\n".join(lines[start - 1 : end]),
        attrs=attrs,
    )


def _sig(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "unknown"
    if "$ref" in schema:
        m = REF_RE.match(str(schema["$ref"]))
        return f"ref:{m.group(1)}" if m else f"ref:{schema['$ref']}"
    t = schema.get("type")
    if t == "array":
        return f"array<{_sig(schema.get('items'))}>"
    if t:
        return str(t)
    return "object" if "properties" in schema else "unknown"


def _media_sig(content: Any) -> str | None:
    if not isinstance(content, dict) or not content:
        return None
    first = next(iter(content.values()))
    return _sig(first.get("schema")) if isinstance(first, dict) else None


def _params(raw: list[Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for p in raw:
        if not isinstance(p, dict) or "name" not in p:
            continue
        out[f"{p['name']}:{p.get('in', '')}"] = {
            "name": p["name"],
            "in": p.get("in", ""),
            "required": bool(p.get("required", False)),
            "type": _sig(p.get("schema")),
        }
    return out


def _endpoint_attrs(op: Mapping, shared_params: list[Any]) -> dict[str, Any]:
    plain = _plain(op)
    body = plain.get("requestBody")
    return {
        "summary": plain.get("summary"),
        "parameters": _params(list(shared_params) + list(plain.get("parameters") or [])),
        "request_body": (
            {
                "required": bool(body.get("required", False)),
                "schema": _media_sig(body.get("content")),
            }
            if isinstance(body, dict)
            else None
        ),
        "responses": {
            str(code): _media_sig(r.get("content")) if isinstance(r, dict) else None
            for code, r in (plain.get("responses") or {}).items()
        },
    }


def _schema_attrs(schema: Mapping) -> dict[str, Any]:
    plain = _plain(schema)
    props = plain.get("properties") or {}
    return {
        "type": plain.get("type"),
        "properties": {str(n): _sig(p) for n, p in props.items()},
        "required": sorted(str(r) for r in (plain.get("required") or [])),
    }


def _ref_edges(source_key: str, node: Any, file: str) -> list[Edge]:
    found: dict[str, int] = {}
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, Mapping):
            ref = cur.get("$ref")
            if isinstance(ref, str):
                m = REF_RE.match(ref)
                if m:
                    line = cur.lc.key("$ref")[0] + 1
                    found[m.group(1)] = min(line, found.get(m.group(1), line))
            stack.extend(v for k, v in cur.items() if k != "$ref")
        elif isinstance(cur, list):
            stack.extend(cur)
    return [
        Edge(
            source_key=source_key,
            target_key=f"schema:{name}",
            relation="uses_schema",
            label=Label.CONFIRMED,
            confidence=1.0,
            evidence=Location(file=file, line_start=line, line_end=line),
            reason=f"$ref to #/components/schemas/{name}",
        )
        for name, line in sorted(found.items())
    ]
