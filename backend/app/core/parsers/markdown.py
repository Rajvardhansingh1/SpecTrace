import hashlib
import json
import re
from dataclasses import dataclass, field

from app.core.limits import Limits
from app.core.models import Entity, EntityKind, Location, ParseResult, RawRef, RawRefKind
from app.errors import LimitExceeded

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)\s*([\w+-]*)")
REQ_ID_RE = re.compile(r"^\s*(?:[-*]\s+)?(REQ-\d+)\s*[:.\-]\s*(.+)$")
RFC_RE = re.compile(r"\b(?:MUST NOT|MUST|SHALL NOT|SHALL|SHOULD NOT|SHOULD|REQUIRED)\b")
ENDPOINT_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[^\s`'\")\]>]*)")
CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
LINK_RE = re.compile(r"\[[^\]]*\]\(#([^)\s]+)\)")
REQ_MENTION_RE = re.compile(r"\bREQ-\d+\b")
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class _Section:
    key: str
    slug: str
    name: str
    start: int
    last_line: int
    body: list[str] = field(default_factory=list)
    refs: list[RawRef] = field(default_factory=list)
    example_n: int = 0
    req_n: int = 0


def parse_markdown(file: str, text: str, limits: Limits) -> ParseResult:
    lines = text.splitlines()
    result = ParseResult()
    slug_counts: dict[str, int] = {}
    seen_req_ids: set[str] = set()
    sec: _Section | None = None

    def new_section(slug_base: str, name: str, start: int, first_line: str | None) -> _Section:
        count = slug_counts.get(slug_base, 0)
        slug_counts[slug_base] = count + 1
        slug = slug_base if count == 0 else f"{slug_base}-{count}"
        s = _Section(f"section:{file}#{slug}", slug, name, start, start)
        if first_line is not None:
            s.body.append(first_line)
        return s

    def flush() -> None:
        if sec is None:
            return
        body = "\n".join(sec.body)
        if sec.slug == "preamble" and not body.strip():
            return
        result.entities.append(
            Entity(
                key=sec.key,
                kind=EntityKind.SECTION,
                name=sec.name,
                location=Location(
                    file=file, line_start=sec.start, line_end=max(sec.last_line, sec.start)
                ),
                content_hash=_hash(body),
                text=body,
                attrs={"slug": sec.slug},
            )
        )
        result.raw_refs.extend(sec.refs)

    i = 0
    while i < len(lines):
        n, line = i + 1, lines[i]

        fence = FENCE_RE.match(line)
        if fence:
            if sec is None:
                sec = new_section("preamble", "Preamble", n, None)
            marker, lang = fence.group(1), fence.group(2).lower()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith(marker):
                j += 1
            if j >= len(lines):
                result.warnings.append(f"{file}:{n}: unterminated code fence")
            end_idx = min(j, len(lines) - 1)
            sec.example_n += 1
            key = f"example:{file}#{sec.slug}:{sec.example_n}"
            block = "\n".join(lines[i : end_idx + 1])
            loc = Location(file=file, line_start=n, line_end=end_idx + 1)
            result.entities.append(
                Entity(
                    key=key,
                    kind=EntityKind.EXAMPLE,
                    name=f"{sec.name} example {sec.example_n}",
                    location=loc,
                    content_hash=_hash(block),
                    text=block,
                    attrs={"language": lang},
                )
            )
            if lang == "json":
                keys = _json_keys("\n".join(lines[i + 1 : j]))
                if keys:
                    result.raw_refs.append(
                        RawRef(
                            source_key=key,
                            kind=RawRefKind.JSON_KEYS,
                            value=",".join(sorted(keys)),
                            location=loc,
                        )
                    )
            sec.last_line = end_idx + 1
            i = end_idx + 1
            continue

        heading = HEADING_RE.match(line)
        if heading:
            flush()
            name = heading.group(2).strip()
            sec = new_section(_slugify(name), name, n, line)
            i += 1
            continue

        if sec is None:
            sec = new_section("preamble", "Preamble", n, None)

        req = REQ_ID_RE.match(line)
        if req or (line.strip() and RFC_RE.search(line)):
            rid = req.group(1) if req else None
            if rid:
                if rid in seen_req_ids:
                    result.warnings.append(f"{file}:{n}: duplicate requirement id {rid}; ignored")
                    i += 1
                    continue
                seen_req_ids.add(rid)
                key, name = f"requirement:{rid}", rid
            else:
                sec.req_n += 1
                key, name = f"requirement:{file}#{sec.slug}:{sec.req_n}", line.strip()[:60]
            result.entities.append(
                Entity(
                    key=key,
                    kind=EntityKind.REQUIREMENT,
                    name=name,
                    location=Location(file=file, line_start=n, line_end=n),
                    content_hash=_hash(line),
                    text=line.strip(),
                    attrs={
                        "id": rid,
                        "section": sec.slug,
                        "keywords": sorted(set(RFC_RE.findall(line))),
                    },
                )
            )
            result.raw_refs.extend(_line_refs(key, line, n, file, skip_req=rid))
            sec.last_line = n
        else:
            sec.body.append(line)
            if line.strip():
                sec.last_line = n
                sec.refs.extend(_line_refs(sec.key, line, n, file))
        i += 1

    flush()
    if len(result.entities) > limits.max_entities:
        raise LimitExceeded(f"{file}: too many entities")
    return result


def _hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


def _slugify(heading: str) -> str:
    s = re.sub(r"[^\w\s-]", "", heading.lower()).strip()
    return re.sub(r"\s+", "-", s) or "section"


def _json_keys(text: str) -> set[str] | None:
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if isinstance(data, list) and data:
        data = data[0]
    return set(data.keys()) if isinstance(data, dict) and data else None


def _line_refs(
    source_key: str, line: str, n: int, file: str, skip_req: str | None = None
) -> list[RawRef]:
    loc = Location(file=file, line_start=n, line_end=n)
    found: dict[tuple[RawRefKind, str], RawRef] = {}

    def add(kind: RawRefKind, value: str) -> None:
        found.setdefault(
            (kind, value), RawRef(source_key=source_key, kind=kind, value=value, location=loc)
        )

    for m in ENDPOINT_RE.finditer(line):
        add(RawRefKind.ENDPOINT, f"{m.group(1)} {m.group(2).rstrip('.,;:')}")
    for m in LINK_RE.finditer(line):
        add(RawRefKind.ANCHOR, m.group(1))
    for rid in REQ_MENTION_RE.findall(line):
        if rid != skip_req:
            add(RawRefKind.REQUIREMENT, rid)
    for m in CODE_SPAN_RE.finditer(line):
        if IDENT_RE.match(m.group(1)):
            add(RawRefKind.IDENTIFIER, m.group(1))
    return list(found.values())
