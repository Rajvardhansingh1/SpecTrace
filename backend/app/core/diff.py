import difflib

from app.core.graph import Graph
from app.core.models import Change, ChangeType, Classification, Entity, EntityKind

_DOC_ONLY = ["no contract change detected; documentation or metadata only"]


def diff_graphs(a: Graph, b: Graph) -> list[Change]:
    changes = []
    for key in sorted(set(a.entities) | set(b.entities)):
        ea, eb = a.entities.get(key), b.entities.get(key)
        if ea is None:
            change_type = ChangeType.ADDED
            cls, reasons = _classify_added_removed(eb, added=True)
        elif eb is None:
            change_type = ChangeType.REMOVED
            cls, reasons = _classify_added_removed(ea, added=False)
        elif ea.content_hash != eb.content_hash:
            change_type = ChangeType.MODIFIED
            cls, reasons = _classify_modified(ea, eb)
        else:
            continue
        ref = eb or ea
        changes.append(
            Change(
                key=key,
                kind=ref.kind,
                change_type=change_type,
                classification=cls,
                reasons=reasons,
                source_diff=_source_diff(ea, eb),
                before=ea.location if ea else None,
                after=eb.location if eb else None,
            )
        )
    return changes


def _source_diff(ea: Entity | None, eb: Entity | None) -> str:
    old = ea.text.splitlines() if ea else []
    new = eb.text.splitlines() if eb else []
    name_a = f"A:{ea.location.file}:{ea.location.line_start}" if ea else "A:/dev/null"
    name_b = f"B:{eb.location.file}:{eb.location.line_start}" if eb else "B:/dev/null"
    return "\n".join(difflib.unified_diff(old, new, name_a, name_b, lineterm=""))


def _classify_added_removed(e: Entity, added: bool) -> tuple[Classification, list[str]]:
    verb = "added" if added else "removed"
    if e.kind in (EntityKind.ENDPOINT, EntityKind.SCHEMA):
        cls = Classification.NON_BREAKING if added else Classification.BREAKING
        return cls, [f"{e.kind.value} {verb}"]
    if e.kind is EntityKind.REQUIREMENT:
        return Classification.UNKNOWN, [
            f"requirement {verb}; effect not classified deterministically"
        ]
    return Classification.DOCUMENTATION, [f"{e.kind.value} {verb}"]


def _classify_modified(ea: Entity, eb: Entity) -> tuple[Classification, list[str]]:
    if ea.kind is EntityKind.ENDPOINT:
        return _classify_endpoint(ea.attrs, eb.attrs)
    if ea.kind is EntityKind.SCHEMA:
        return _classify_schema(ea.attrs, eb.attrs)
    if ea.kind is EntityKind.REQUIREMENT:
        reasons = ["requirement text changed; effect not classified deterministically"]
        if ea.attrs.get("keywords") != eb.attrs.get("keywords"):
            reasons.append(f"keywords {ea.attrs.get('keywords')} -> {eb.attrs.get('keywords')}")
        return Classification.UNKNOWN, reasons
    return Classification.DOCUMENTATION, ["text changed"]


def _verdict(breaking: list[str], unknown: list[str], non_breaking: list[str]):
    if breaking:
        return Classification.BREAKING, breaking
    if unknown:
        return Classification.UNKNOWN, unknown
    if non_breaking:
        return Classification.NON_BREAKING, non_breaking
    return Classification.DOCUMENTATION, list(_DOC_ONLY)


def _classify_endpoint(a: dict, b: dict):
    breaking, unknown, non_breaking = [], [], []
    pa, pb = a["parameters"], b["parameters"]
    for k, p in pb.items():
        if k not in pa:
            if p["required"]:
                breaking.append(f"parameter {p['name']} ({p['in']}) added as required")
            else:
                non_breaking.append(f"parameter {p['name']} ({p['in']}) added")
        else:
            old = pa[k]
            if old["type"] != p["type"]:
                breaking.append(f"parameter {p['name']} type changed {old['type']} -> {p['type']}")
            if p["required"] and not old["required"]:
                breaking.append(f"parameter {p['name']} became required")
    for k, p in pa.items():
        if k not in pb:
            unknown.append(f"parameter {p['name']} ({p['in']}) removed")

    ra, rb = a["request_body"], b["request_body"]
    if rb and rb["required"] and not (ra and ra["required"]):
        breaking.append("request body became required")
    if ra and rb and ra["schema"] != rb["schema"]:
        breaking.append(f"request body schema changed {ra['schema']} -> {rb['schema']}")
    if ra and not rb:
        unknown.append("request body removed")

    sa, sb = a["responses"], b["responses"]
    for code, sig in sa.items():
        if code not in sb:
            (breaking if code.startswith("2") else unknown).append(f"response {code} removed")
        elif sb[code] != sig:
            breaking.append(f"response {code} schema changed {sig} -> {sb[code]}")
    non_breaking.extend(f"response {code} added" for code in sb if code not in sa)
    return _verdict(breaking, unknown, non_breaking)


def _classify_schema(a: dict, b: dict):
    breaking, non_breaking = [], []
    pa, pb = a["properties"], b["properties"]
    ra, rb = set(a["required"]), set(b["required"])
    for name, sig in pa.items():
        if name not in pb:
            breaking.append(f"property {name} removed")
        elif pb[name] != sig:
            breaking.append(f"property {name} type changed {sig} -> {pb[name]}")
    for name in pb:
        if name not in pa:
            if name in rb:
                breaking.append(f"property {name} added as required")
            else:
                non_breaking.append(f"property {name} added")
    breaking.extend(f"property {n} became required" for n in sorted(rb - ra) if n in pa)
    non_breaking.extend(f"property {n} no longer required" for n in sorted(ra - rb) if n in pb)
    if a["type"] != b["type"]:
        breaking.append(f"schema type changed {a['type']} -> {b['type']}")
    return _verdict(breaking, [], non_breaking)
