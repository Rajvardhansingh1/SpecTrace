# Backend Core Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tested, pure-Python engine that takes two versions of OpenAPI + Markdown files and returns changes, a dependency graph with confirmed/inferred edges, and evidence-path impact reports, exposed so far only through a FastAPI `/health` app shell.

**Architecture:** Deterministic parsers produce typed entities, direct edges and raw references. `graph.py` resolves raw references into labeled edges. `diff.py` compares entities by stable key and classifies changes with fixed rules. `impact.py` searches reverse edges for evidence paths. `pipeline.py` wires them with input limits. No database, network or LLM in this plan.

**Tech Stack:** Python 3.13.16 (conda env `SpecTrace`), FastAPI 0.143.2, pydantic 2.14.1, pydantic-settings 2.16.0, ruamel.yaml 0.19.1 (round-trip loader, gives line numbers), pytest 9.1.1, ruff 0.17.1.

**Spec:** `DOCS/superpowers/specs/2026-10-16-spectrace-design.md`

## Global Constraints

- Run every Python command through the conda env's own interpreter: `conda run -n SpecTrace --cwd backend python -m <module>` (the non-interactive equivalent of `conda activate SpecTrace`). Always use `python -m pytest` / `python -m ruff`, never bare `pytest`: when the env lacked Python, bare commands silently fell through PATH to `C:\Python314` and base Anaconda.
- Commands below written as `pytest ...` mean `conda run -n SpecTrace --cwd backend python -m pytest ...`.
- Domain code under `backend/app/core/` must not import from `app.api`, `app.adapters`, `fastapi` or any database library.
- YAML is parsed only with `ruamel.yaml` `YAML(typ="rt")`. No `eval`, `pickle`, or unsafe loaders.
- Edge labels: `confirmed` only for `$ref`, `METHOD /path` mentions that match an endpoint, anchor links to existing sections, and existing requirement IDs. Everything else is `inferred`.
- `Testing.md` is never modified.
- Do not add dependencies beyond those listed in Task 0 without asking.
- Docs (`State.md`, `Decision.md`, `Explain.md`, `Design_graph.md`) are updated in Task 9, from what actually exists.

---

## File Structure

```
SpecTrace/
  backend/
    pyproject.toml
    requirements.txt             pinned runtime deps (Render installs this)
    requirements-dev.txt         test and lint deps
    app/
      __init__.py
      errors.py                  stable error classes and codes
      config.py                  Settings
      main.py                    create_app(), /health, error envelope, CORS
      core/
        __init__.py
        models.py                Location, Entity, Edge, RawRef, ParseResult, Change, Impact
        limits.py                Limits dataclass
        parsers/
          __init__.py
          openapi.py             parse_openapi()
          markdown.py            parse_markdown()
        graph.py                 Graph, build_graph()
        diff.py                  diff_graphs()
        impact.py                find_impacts()
        pipeline.py              analyze(), answer_question()
    tests/
      conftest.py                sample loaders
      helpers.py                 graph_of()
      test_health.py
      test_models.py
      test_openapi_parser.py
      test_markdown_parser.py
      test_graph.py
      test_diff.py
      test_impact.py
      test_pipeline.py
      test_regression_scenarios.py
  samples/petstore/
    v1/openapi.yaml  v1/docs/guide.md
    v2/openapi.yaml  v2/docs/guide.md
```

---

### Task 0: Environment and repository

**Files:** `.gitignore`, `.gitattributes`.

- [x] **Step 1: Give the env its own Python** (done 2026-10-16). The env had no interpreter; `conda install -n SpecTrace python=3.13 pip` installed 3.13.16. 3.13 was chosen over 3.14 because every compiled dependency (`pydantic-core`, `psycopg-binary`, `ruamel.yaml`, `coverage`) has a `cp313` wheel and Render supports 3.13.

- [x] **Step 2: Install dependencies** (done 2026-10-16, `pip check` clean): fastapi 0.143.2, uvicorn 0.54.0, python-multipart 0.0.32, psycopg[binary] 3.3.6, pydantic 2.14.1, pydantic-settings 2.16.0, ruamel.yaml 0.19.1, SQLAlchemy 2.1.4, alembic 1.20.0, httpx 0.28.1, pytest 9.1.1, pytest-cov 7.1.0, ruff 0.17.1.

- [ ] **Step 3: Verify the interpreter is the env's own**

Run: `conda run -n SpecTrace python -c "import sys, fastapi, ruamel.yaml; print(sys.executable)"`
Expected: `D:\Anaconda3\envs\SpecTrace\python.exe`. Any other path means PATH fallthrough; stop.

- [ ] **Step 4: Initialize git (requires user authorization; not yet given)**

Create `SpecTrace/.gitattributes` so sample files keep LF endings and stable line numbers on Windows:

```
* text=auto eol=lf
```

Create `SpecTrace/.gitignore`:

```
__pycache__/
.DOCS/
*.pyc
.pytest_cache/
.ruff_cache/
.coverage
.env
.env.*
!.env.example
node_modules/
.next/
*.sqlite3
```

Run: `git init` in `SpecTrace/`, then `git add DOCS .gitignore .gitattributes` and commit `chore: add project docs and gitignore`.

---

### Task 1: Backend scaffold, settings, errors, `/health`

**Files:**
- Create: `backend/pyproject.toml`, `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/app/__init__.py`, `backend/app/errors.py`, `backend/app/config.py`, `backend/app/main.py`
- Create: `backend/app/core/__init__.py`, `backend/app/core/parsers/__init__.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `app.errors.{SpecTraceError, InputTooLarge, UnsupportedInput, ParseError, LimitExceeded}` each with `.code: str`, `.status: int`, `.message: str`; `app.config.Settings`; `app.main.create_app(settings: Settings | None = None) -> FastAPI`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_health.py`

```python
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import ParseError
from app.main import create_app


def make_client(**overrides):
    # _env_file=None: a developer's local .env must not change test outcomes.
    app = create_app(Settings(_env_file=None, **overrides))

    @app.get("/boom")
    def boom():
        raise ParseError("bad input")

    return TestClient(app)


def test_health_ok():
    r = make_client().get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_spectrace_error_uses_stable_envelope():
    r = make_client().get("/boom")
    assert r.status_code == 422
    assert r.json() == {"error": {"code": "parse_error", "message": "bad input"}}


def test_cors_allows_configured_origin_only():
    client = make_client(cors_origins=["http://localhost:3000"])
    ok = client.get("/health", headers={"Origin": "http://localhost:3000"})
    bad = client.get("/health", headers={"Origin": "https://evil.example"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in bad.headers
```

- [ ] **Step 2: Run to verify it fails**

Run: `conda run -n SpecTrace pytest tests/test_health.py -v` (cwd `backend/`)
Expected: FAIL, `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 3: Write the implementation**

`backend/pyproject.toml`:

```toml
[project]
name = "spectrace-backend"
version = "0.1.0"
requires-python = ">=3.13,<3.14"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

`backend/app/__init__.py`: `__version__ = "0.1.0"`

`backend/app/errors.py`:

```python
class SpecTraceError(Exception):
    code = "internal_error"
    status = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InputTooLarge(SpecTraceError):
    code = "input_too_large"
    status = 413


class UnsupportedInput(SpecTraceError):
    code = "unsupported_input"
    status = 415


class ParseError(SpecTraceError):
    code = "parse_error"
    status = 422


class LimitExceeded(SpecTraceError):
    code = "limit_exceeded"
    status = 422
```

`backend/app/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPECTRACE_", env_file=".env", extra="ignore")

    database_url: str | None = None
    cors_origins: list[str] = ["http://localhost:3000"]
```

`backend/app/main.py`:

```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import Settings
from app.errors import SpecTraceError


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
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
```

Create empty `backend/app/core/__init__.py` and `backend/app/core/parsers/__init__.py`.

- [ ] **Step 4: Run to verify it passes**

Run: `conda run -n SpecTrace pytest tests/test_health.py -v`
Expected: 3 passed.

- [ ] **Step 5: Pin dependencies and commit**

Create `backend/requirements.txt` with the direct dependencies pinned to the installed versions (do **not** use `pip freeze`: in a conda env it emits `@ file:///` paths that Render cannot install):

```
fastapi==0.143.2
uvicorn==0.54.0
python-multipart==0.0.32
pydantic==2.14.1
pydantic-settings==2.16.0
ruamel.yaml==0.19.1
SQLAlchemy==2.1.4
alembic==1.20.0
psycopg[binary]==3.3.6
httpx==0.28.1
```

and `backend/requirements-dev.txt`:

```
-r requirements.txt
pytest==9.1.1
pytest-cov==7.1.0
ruff==0.17.1
```

Verify: `conda run -n SpecTrace python -m pip install --dry-run -r backend/requirements-dev.txt` reports nothing new to install. Commit `feat: backend scaffold with health endpoint and error envelope`.

---

### Task 2: Domain models and limits

**Files:**
- Create: `backend/app/core/models.py`, `backend/app/core/limits.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces (all in `app.core.models`): `EntityKind`, `Label`, `ChangeType`, `Classification`, `RawRefKind` (`StrEnum`s); frozen models `Location(file, line_start, line_end)`, `Entity(key, kind, name, location, content_hash, text, attrs)`, `Edge(source_key, target_key, relation, label, confidence, evidence, reason)`, `RawRef(source_key, kind, value, location)`; `ParseResult(entities, edges, raw_refs, warnings)`; `Change(key, kind, change_type, classification, reasons, source_diff, before, after)`; `Impact(change_key, impacted_key, certainty, confidence, path, confirmed_breaking, summary)`. `app.core.limits.Limits` dataclass with defaults `max_files=200, max_file_bytes=1_000_000, max_total_bytes=5_000_000, max_entities=20_000, max_yaml_nodes=200_000, max_yaml_depth=50`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_models.py`

```python
import pytest
from pydantic import ValidationError

from app.core.limits import Limits
from app.core.models import Entity, EntityKind, Location


def test_location_requires_positive_lines():
    with pytest.raises(ValidationError):
        Location(file="a.md", line_start=0, line_end=1)


def test_entity_is_frozen():
    e = Entity(
        key="schema:Pet",
        kind=EntityKind.SCHEMA,
        name="Pet",
        location=Location(file="a.yaml", line_start=1, line_end=2),
        content_hash="h",
        text="t",
    )
    with pytest.raises(ValidationError):
        e.key = "x"


def test_limits_defaults_are_bounded():
    limits = Limits()
    assert limits.max_file_bytes <= limits.max_total_bytes
    assert limits.max_yaml_depth > 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `conda run -n SpecTrace pytest tests/test_models.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.core.models'`.

- [ ] **Step 3: Write the implementation**

`backend/app/core/limits.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    max_files: int = 200
    max_file_bytes: int = 1_000_000
    max_total_bytes: int = 5_000_000
    max_entities: int = 20_000
    max_yaml_nodes: int = 200_000
    max_yaml_depth: int = 50
```

`backend/app/core/models.py`:

```python
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EntityKind(StrEnum):
    ENDPOINT = "endpoint"
    SCHEMA = "schema"
    SECTION = "section"
    REQUIREMENT = "requirement"
    EXAMPLE = "example"


class Label(StrEnum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"


class ChangeType(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


class Classification(StrEnum):
    BREAKING = "breaking"
    NON_BREAKING = "non_breaking"
    DOCUMENTATION = "documentation"
    UNKNOWN = "unknown"


class RawRefKind(StrEnum):
    ENDPOINT = "endpoint"
    ANCHOR = "anchor"
    REQUIREMENT = "requirement"
    IDENTIFIER = "identifier"
    JSON_KEYS = "json_keys"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Location(_Frozen):
    file: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)


class Entity(_Frozen):
    key: str
    kind: EntityKind
    name: str
    location: Location
    content_hash: str
    text: str
    attrs: dict[str, Any] = Field(default_factory=dict)


class Edge(_Frozen):
    """`source_key` depends on `target_key`."""

    source_key: str
    target_key: str
    relation: str
    label: Label
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: Location
    reason: str


class RawRef(_Frozen):
    source_key: str
    kind: RawRefKind
    value: str
    location: Location


class ParseResult(BaseModel):
    entities: list[Entity] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    raw_refs: list[RawRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Change(_Frozen):
    key: str
    kind: EntityKind
    change_type: ChangeType
    classification: Classification
    reasons: list[str]
    source_diff: str
    before: Location | None = None
    after: Location | None = None


class Impact(_Frozen):
    change_key: str
    impacted_key: str
    certainty: Label
    confidence: float
    path: list[Edge]
    confirmed_breaking: bool
    summary: str
```

- [ ] **Step 4: Run to verify it passes**

Run: `conda run -n SpecTrace pytest tests/test_models.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit** `feat: domain models and limits`

---

### Task 3: Petstore sample data and OpenAPI parser

**Files:**
- Create: `samples/petstore/v1/openapi.yaml`, `samples/petstore/v2/openapi.yaml`, `samples/petstore/v1/docs/guide.md`, `samples/petstore/v2/docs/guide.md`
- Create: `backend/app/core/parsers/openapi.py`, `backend/tests/conftest.py`
- Test: `backend/tests/test_openapi_parser.py`

**Interfaces:**
- Consumes: `Limits`, models, `ParseError`, `UnsupportedInput`, `LimitExceeded`.
- Produces: `parse_openapi(file: str, text: str, limits: Limits) -> ParseResult`. Entity keys `endpoint:<METHOD> <path>` and `schema:<Name>`. Endpoint `attrs`: `{"summary", "parameters": {"<name>:<in>": {"name","in","required","type"}}, "request_body": {"required","schema"} | None, "responses": {"<code>": "<sig>" | None}}`. Schema `attrs`: `{"type", "properties": {name: sig}, "required": [sorted names]}`. Edges: relation `uses_schema`, label `confirmed`, confidence `1.0`, evidence at the `$ref` line. Signatures: `string`, `array<ref:Pet>`, `ref:Pet`, `unknown`.

- [ ] **Step 1: Create the sample data**

`samples/petstore/v1/openapi.yaml`:

```yaml
openapi: 3.0.3
info:
  title: Petstore
  version: "1.0.0"
paths:
  /pets:
    get:
      summary: List pets
      parameters:
        - name: limit
          in: query
          required: false
          schema:
            type: integer
      responses:
        "200":
          description: A list of pets
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Pet"
    post:
      summary: Create a pet
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/NewPet"
      responses:
        "201":
          description: Created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Pet"
  /pets/{petId}:
    get:
      summary: Get a pet
      parameters:
        - name: petId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: A pet
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Pet"
  /owners:
    get:
      summary: List owners
      responses:
        "200":
          description: A list of owners
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Owner"
components:
  schemas:
    Pet:
      type: object
      required: [id, name]
      properties:
        id:
          type: string
        name:
          type: string
        tag:
          type: string
    NewPet:
      type: object
      required: [name]
      properties:
        name:
          type: string
        tag:
          type: string
    Owner:
      type: object
      required: [id]
      properties:
        id:
          type: string
        email:
          type: string
```

`samples/petstore/v2/openapi.yaml`: identical to v1 except `info.version: "1.1.0"` and `Pet.properties.id.type: integer` (the single breaking change).

`samples/petstore/v1/docs/guide.md` (and `v2/docs/guide.md` identical, because the docs were not updated; they are now stale):

````markdown
# Petstore Guide

## Listing pets
Call `GET /pets` to list all pets. Each item is a `Pet`.

## Fetching a pet
Call `GET /pets/{petId}` to fetch one pet.

REQ-001: Clients MUST treat the `Pet` id as an opaque string.

```json
{"id": "p-1", "name": "Rex", "tag": "dog"}
```

## Owners
Call `GET /owners` to list owners.
````

`backend/tests/conftest.py`:

```python
from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "petstore"


def load_version(version: str) -> dict[str, str]:
    root = SAMPLES / version
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def v1() -> dict[str, str]:
    return load_version("v1")


@pytest.fixture
def v2() -> dict[str, str]:
    return load_version("v2")
```

- [ ] **Step 2: Write the failing test** — `backend/tests/test_openapi_parser.py`

```python
import pytest

from app.core.limits import Limits
from app.core.models import EntityKind, Label
from app.core.parsers.openapi import parse_openapi
from app.errors import LimitExceeded, ParseError, UnsupportedInput

LIMITS = Limits()


def parse(v1):
    return parse_openapi("openapi.yaml", v1["openapi.yaml"], LIMITS)


def test_extracts_endpoints_and_schemas(v1):
    keys = {e.key for e in parse(v1).entities}
    assert keys == {
        "endpoint:GET /pets",
        "endpoint:POST /pets",
        "endpoint:GET /pets/{petId}",
        "endpoint:GET /owners",
        "schema:Pet",
        "schema:NewPet",
        "schema:Owner",
    }


def test_endpoint_location_points_at_method_line(v1):
    lines = v1["openapi.yaml"].splitlines()
    path_idx = lines.index("  /pets/{petId}:")
    method_line = next(i for i in range(path_idx, len(lines)) if lines[i].strip() == "get:") + 1
    ent = {e.key: e for e in parse(v1).entities}["endpoint:GET /pets/{petId}"]
    assert ent.location.line_start == method_line
    assert ent.text.splitlines()[0].strip() == "get:"


def test_ref_edges_are_confirmed_with_line_evidence(v1):
    result = parse(v1)
    lines = v1["openapi.yaml"].splitlines()
    edge = next(
        e for e in result.edges
        if e.source_key == "endpoint:GET /pets" and e.target_key == "schema:Pet"
    )
    assert edge.label is Label.CONFIRMED
    assert edge.confidence == 1.0
    assert "$ref" in lines[edge.evidence.line_start - 1]
    assert "Pet" in lines[edge.evidence.line_start - 1]


def test_endpoint_attrs(v1):
    ent = {e.key: e for e in parse(v1).entities}["endpoint:GET /pets"]
    assert ent.kind is EntityKind.ENDPOINT
    assert ent.attrs["parameters"]["limit:query"] == {
        "name": "limit", "in": "query", "required": False, "type": "integer"
    }
    assert ent.attrs["responses"]["200"] == "array<ref:Pet>"


def test_schema_attrs(v1):
    ent = {e.key: e for e in parse(v1).entities}["schema:Pet"]
    assert ent.attrs["properties"] == {"id": "string", "name": "string", "tag": "string"}
    assert ent.attrs["required"] == ["id", "name"]


def test_hash_ignores_comments_and_formatting(v1):
    changed = v1["openapi.yaml"].replace("summary: Get a pet", "summary: Get a pet   # note")
    a = {e.key: e.content_hash for e in parse(v1).entities}
    b = {e.key: e.content_hash for e in parse_openapi("openapi.yaml", changed, LIMITS).entities}
    assert a == b


def test_rejects_non_openapi_document():
    with pytest.raises(UnsupportedInput):
        parse_openapi("x.yaml", "name: not-openapi\n", LIMITS)


def test_rejects_invalid_yaml():
    with pytest.raises(ParseError):
        parse_openapi("x.yaml", "openapi: [unclosed\n", LIMITS)


def test_rejects_alias_expansion_bomb():
    lines = ["openapi: 3.0.0", "l0: &l0 [" + ", ".join(["x"] * 10) + "]"]
    for i in range(1, 9):
        lines.append(f"l{i}: &l{i} [" + ", ".join([f"*l{i - 1}"] * 10) + "]")
    with pytest.raises(LimitExceeded):
        parse_openapi("bomb.yaml", "\n".join(lines) + "\n", LIMITS)


@pytest.mark.parametrize("depth", [100, 5000])
def test_rejects_deep_nesting(depth):
    text = "openapi: 3.0.0\nx: " + "[" * depth + "]" * depth + "\n"
    with pytest.raises(LimitExceeded):
        parse_openapi("deep.yaml", text, LIMITS)
```

- [ ] **Step 3: Run to verify it fails**

Run: `conda run -n SpecTrace pytest tests/test_openapi_parser.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.core.parsers.openapi'`.

- [ ] **Step 4: Write the implementation** — `backend/app/core/parsers/openapi.py`

```python
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
                        key, EntityKind.ENDPOINT, f"{method.upper()} {path}", file, lines,
                        start, end, op, _endpoint_attrs(op, shared),
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
                        key, EntityKind.SCHEMA, str(name), file, lines,
                        start, end, schema, _schema_attrs(schema),
                    )
                )
                result.edges.extend(
                    e for e in _ref_edges(key, schema, file) if e.target_key != key
                )

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
            {"required": bool(body.get("required", False)), "schema": _media_sig(body.get("content"))}
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
```

- [ ] **Step 5: Run to verify it passes**

Run: `conda run -n SpecTrace pytest tests/test_openapi_parser.py -v`
Expected: all pass. If `test_rejects_alias_expansion_bomb` hangs or passes parsing, stop and diagnose before proceeding: the node cap is a security control.

- [ ] **Step 6: Commit** `feat: OpenAPI parser with line evidence and parsing bounds`

---

### Task 4: Markdown parser

**Files:**
- Create: `backend/app/core/parsers/markdown.py`
- Test: `backend/tests/test_markdown_parser.py`

**Interfaces:**
- Consumes: models, `Limits`.
- Produces: `parse_markdown(file: str, text: str, limits: Limits) -> ParseResult`. Entity keys: `section:<file>#<slug>`, `requirement:REQ-###` (ID'd) or `requirement:<file>#<slug>:<n>` (RFC 2119 keyword, no ID), `example:<file>#<slug>:<n>`. `RawRef` kinds: `endpoint` (value `"GET /pets"`), `anchor` (value is the slug), `requirement` (value `"REQ-002"`), `identifier` (value is a backticked identifier), `json_keys` (value is comma-joined sorted top-level keys). Section `text` excludes requirement lines and fenced blocks, so one edit does not mark several entities changed.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_markdown_parser.py`

```python
from app.core.limits import Limits
from app.core.models import EntityKind, RawRefKind
from app.core.parsers.markdown import parse_markdown

LIMITS = Limits()


def parse(v1):
    return parse_markdown("docs/guide.md", v1["docs/guide.md"], LIMITS)


def refs_of(result, key):
    return {(r.kind, r.value) for r in result.raw_refs if r.source_key == key}


def test_extracts_sections_requirement_and_example(v1):
    keys = {e.key for e in parse(v1).entities}
    assert keys == {
        "section:docs/guide.md#petstore-guide",
        "section:docs/guide.md#listing-pets",
        "section:docs/guide.md#fetching-a-pet",
        "section:docs/guide.md#owners",
        "requirement:REQ-001",
        "example:docs/guide.md#fetching-a-pet:1",
    }


def test_locations(v1):
    ents = {e.key: e for e in parse(v1).entities}
    req = ents["requirement:REQ-001"]
    assert (req.location.line_start, req.location.line_end) == (9, 9)
    ex = ents["example:docs/guide.md#fetching-a-pet:1"]
    assert (ex.location.line_start, ex.location.line_end) == (11, 13)
    assert ex.attrs["language"] == "json"


def test_section_text_excludes_requirement_and_example(v1):
    sec = {e.key: e for e in parse(v1).entities}["section:docs/guide.md#fetching-a-pet"]
    assert "REQ-001" not in sec.text
    assert '"id"' not in sec.text
    assert "GET /pets/{petId}" in sec.text


def test_raw_references(v1):
    result = parse(v1)
    assert refs_of(result, "section:docs/guide.md#listing-pets") == {
        (RawRefKind.ENDPOINT, "GET /pets"),
        (RawRefKind.IDENTIFIER, "Pet"),
    }
    assert (RawRefKind.ENDPOINT, "GET /pets/{petId}") in refs_of(
        result, "section:docs/guide.md#fetching-a-pet"
    )
    assert refs_of(result, "requirement:REQ-001") == {(RawRefKind.IDENTIFIER, "Pet")}
    assert refs_of(result, "example:docs/guide.md#fetching-a-pet:1") == {
        (RawRefKind.JSON_KEYS, "id,name,tag")
    }


def test_headings_inside_fences_are_ignored():
    text = "# Title\n\n```\n# not a heading\n```\n"
    keys = {e.key for e in parse_markdown("a.md", text, LIMITS).entities}
    assert keys == {"section:a.md#title", "example:a.md#title:1"}


def test_duplicate_headings_get_unique_slugs():
    text = "## Setup\none\n\n## Setup\ntwo\n"
    keys = {e.key for e in parse_markdown("a.md", text, LIMITS).entities}
    assert keys == {"section:a.md#setup", "section:a.md#setup-1"}


def test_rfc2119_line_without_id_becomes_requirement():
    text = "## Auth\nThe server MUST reject unsigned tokens.\n"
    ents = parse_markdown("a.md", text, LIMITS).entities
    req = next(e for e in ents if e.kind is EntityKind.REQUIREMENT)
    assert req.key == "requirement:a.md#auth:1"


def test_anchor_and_requirement_mentions():
    text = "## A\nSee [b](#b) and REQ-002.\n\n## B\nbody\n"
    result = parse_markdown("a.md", text, LIMITS)
    assert refs_of(result, "section:a.md#a") == {
        (RawRefKind.ANCHOR, "b"),
        (RawRefKind.REQUIREMENT, "REQ-002"),
    }


def test_whitespace_only_change_keeps_hash():
    a = parse_markdown("a.md", "## A\nhello   world\n", LIMITS).entities[0].content_hash
    b = parse_markdown("a.md", "## A\nhello world\n", LIMITS).entities[0].content_hash
    assert a == b
```

- [ ] **Step 2: Run to verify it fails**

Run: `conda run -n SpecTrace pytest tests/test_markdown_parser.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation** — `backend/app/core/parsers/markdown.py`

```python
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
                location=Location(file=file, line_start=sec.start, line_end=max(sec.last_line, sec.start)),
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
                    key=key, kind=EntityKind.EXAMPLE, name=f"{sec.name} example {sec.example_n}",
                    location=loc, content_hash=_hash(block), text=block, attrs={"language": lang},
                )
            )
            if lang == "json":
                keys = _json_keys("\n".join(lines[i + 1 : j]))
                if keys:
                    result.raw_refs.append(
                        RawRef(source_key=key, kind=RawRefKind.JSON_KEYS, value=",".join(sorted(keys)), location=loc)
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
                    key=key, kind=EntityKind.REQUIREMENT, name=name,
                    location=Location(file=file, line_start=n, line_end=n),
                    content_hash=_hash(line), text=line.strip(),
                    attrs={"id": rid, "section": sec.slug, "keywords": sorted(set(RFC_RE.findall(line)))},
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


def _line_refs(source_key: str, line: str, n: int, file: str, skip_req: str | None = None) -> list[RawRef]:
    loc = Location(file=file, line_start=n, line_end=n)
    found: dict[tuple[RawRefKind, str], RawRef] = {}

    def add(kind: RawRefKind, value: str) -> None:
        found.setdefault((kind, value), RawRef(source_key=source_key, kind=kind, value=value, location=loc))

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
```

- [ ] **Step 4: Run to verify it passes**

Run: `conda run -n SpecTrace pytest tests/test_markdown_parser.py -v`
Expected: all pass.

- [ ] **Step 5: Commit** `feat: Markdown parser for sections, requirements, examples and references`

---

### Task 5: Graph builder with confirmed/inferred labeling

**Files:**
- Create: `backend/app/core/graph.py`, `backend/tests/helpers.py`
- Test: `backend/tests/test_graph.py`

**Interfaces:**
- Consumes: `ParseResult`, models.
- Produces: `Graph(entities: dict[str, Entity], edges: list[Edge], warnings: list[str])`; `build_graph(results: list[ParseResult]) -> Graph`. Edge relations: `uses_schema` (from parser), `mentions_endpoint`, `links_to`, `mentions_requirement` (all `confirmed`, 1.0), `mentions_name` (`inferred`, 0.8), `similar_properties` (`inferred`, 0.6, requires at least 2 shared keys and Jaccard similarity of at least 0.75). Endpoint mentions match ignoring path parameter names and trailing slashes. Unresolved endpoint/anchor/requirement references produce a warning and no edge.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_graph.py`

```python
from app.core.graph import build_graph
from app.core.limits import Limits
from app.core.models import Label
from app.core.parsers.markdown import parse_markdown
from helpers import graph_of

LIMITS = Limits()


def edge(graph, source, target):
    return next((e for e in graph.edges if e.source_key == source and e.target_key == target), None)


def test_docs_reference_endpoints_with_confirmed_edges(v1):
    g = graph_of(v1)
    e = edge(g, "section:docs/guide.md#listing-pets", "endpoint:GET /pets")
    assert e.label is Label.CONFIRMED and e.confidence == 1.0 and e.relation == "mentions_endpoint"
    assert e.evidence.line_start == 4
    assert edge(g, "section:docs/guide.md#fetching-a-pet", "endpoint:GET /pets/{petId}")


def test_backticked_schema_name_is_inferred(v1):
    g = graph_of(v1)
    e = edge(g, "requirement:REQ-001", "schema:Pet")
    assert e.label is Label.INFERRED and e.confidence == 0.8
    assert edge(g, "section:docs/guide.md#listing-pets", "schema:Pet").label is Label.INFERRED


def test_json_example_matches_only_the_closest_schema(v1):
    g = graph_of(v1)
    key = "example:docs/guide.md#fetching-a-pet:1"
    e = edge(g, key, "schema:Pet")
    assert e.label is Label.INFERRED and e.confidence == 0.6
    assert edge(g, key, "schema:NewPet") is None
    assert edge(g, key, "schema:Owner") is None


def test_unrelated_entities_have_no_edges_to_pet(v1):
    g = graph_of(v1)
    assert edge(g, "section:docs/guide.md#owners", "schema:Pet") is None
    assert edge(g, "endpoint:GET /owners", "schema:Pet") is None


def test_endpoint_mention_ignores_parameter_names():
    api = (
        "openapi: 3.0.0\npaths:\n  /pets/{petId}:\n    get:\n      responses:\n"
        '        "200":\n          description: ok\n'
    )
    md = "## A\nCall `GET /pets/{id}`.\n"
    g = graph_of({"openapi.yaml": api, "a.md": md})
    assert edge(g, "section:a.md#a", "endpoint:GET /pets/{petId}").label is Label.CONFIRMED


def test_unresolved_anchor_warns_without_edge():
    r = parse_markdown("a.md", "## A\nSee [x](#missing).\n", LIMITS)
    g = build_graph([r])
    assert g.edges == []
    assert any("missing" in w for w in g.warnings)


def test_anchor_link_to_existing_section_is_confirmed():
    r = parse_markdown("a.md", "## A\nSee [b](#b).\n\n## B\nbody\n", LIMITS)
    e = edge(build_graph([r]), "section:a.md#a", "section:a.md#b")
    assert e.label is Label.CONFIRMED and e.relation == "links_to"
```

`backend/tests/helpers.py`:

```python
from app.core.graph import Graph, build_graph
from app.core.limits import Limits
from app.core.parsers.markdown import parse_markdown
from app.core.parsers.openapi import parse_openapi


def graph_of(files: dict[str, str]) -> Graph:
    limits = Limits()
    results = []
    for name, text in sorted(files.items()):
        if name.endswith((".yaml", ".yml", ".json")):
            results.append(parse_openapi(name, text, limits))
        else:
            results.append(parse_markdown(name, text, limits))
    return build_graph(results)
```

- [ ] **Step 2: Run to verify it fails**

Run: `conda run -n SpecTrace pytest tests/test_graph.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.core.graph'`.

- [ ] **Step 3: Write the implementation** — `backend/app/core/graph.py`

```python
import re
from dataclasses import dataclass, field

from app.core.models import (
    Edge, Entity, EntityKind, Label, ParseResult, RawRef, RawRefKind,
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
            candidates.extend(_resolve(ref, entities, schema_keys, schema_props, endpoints, warnings))

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
        source_key=ref.source_key, target_key=target, relation=relation, label=label,
        confidence=conf, evidence=ref.location, reason=reason,
    )


def _resolve(ref, entities, schema_keys, schema_props, endpoints, warnings) -> list[Edge]:
    if ref.kind is RawRefKind.ENDPOINT:
        method, path = ref.value.split(" ", 1)
        target = endpoints.get((method, _norm_path(path)))
        if target is None:
            warnings.append(f"{ref.location.file}:{ref.location.line_start}: unknown endpoint {ref.value}")
            return []
        return [_edge(ref, target, "mentions_endpoint", Label.CONFIRMED, 1.0, f"mentions {ref.value}")]

    if ref.kind is RawRefKind.ANCHOR:
        source_file = entities[ref.source_key].location.file
        target = f"section:{source_file}#{ref.value}"
        if target not in entities:
            warnings.append(f"{ref.location.file}:{ref.location.line_start}: unresolved anchor #{ref.value}")
            return []
        return [_edge(ref, target, "links_to", Label.CONFIRMED, 1.0, f"link to #{ref.value}")]

    if ref.kind is RawRefKind.REQUIREMENT:
        target = f"requirement:{ref.value}"
        if target not in entities:
            warnings.append(f"{ref.location.file}:{ref.location.line_start}: unknown requirement {ref.value}")
            return []
        return [_edge(ref, target, "mentions_requirement", Label.CONFIRMED, 1.0, f"mentions {ref.value}")]

    if ref.kind is RawRefKind.IDENTIFIER:
        target = schema_keys.get(ref.value)
        if target is None:
            return []
        return [
            _edge(ref, target, "mentions_name", Label.INFERRED, NAME_CONFIDENCE,
                  f"backticked identifier `{ref.value}` equals a schema name")
        ]

    if ref.kind is RawRefKind.JSON_KEYS:
        keys = set(ref.value.split(","))
        edges = []
        for target, props in schema_props.items():
            shared = keys & props
            union = keys | props
            if len(shared) >= PROPERTY_MIN_SHARED and len(shared) / len(union) >= PROPERTY_MIN_JACCARD:
                edges.append(
                    _edge(ref, target, "similar_properties", Label.INFERRED, PROPERTY_CONFIDENCE,
                          f"example keys {sorted(shared)} overlap schema properties")
                )
        return edges
    return []
```

- [ ] **Step 4: Run to verify it passes**

Run: `conda run -n SpecTrace pytest tests/test_graph.py -v`
Expected: all pass. If `test_json_example_matches_only_the_closest_schema` fails on NewPet, the Jaccard threshold is wrong; fix the threshold, not the test.

- [ ] **Step 5: Commit** `feat: dependency graph with confirmed and inferred edges`

---

### Task 6: Differ with deterministic classification

**Files:**
- Create: `backend/app/core/diff.py`
- Test: `backend/tests/test_diff.py`

**Interfaces:**
- Consumes: `Graph`, models.
- Produces: `diff_graphs(a: Graph, b: Graph) -> list[Change]` sorted by key. A change exists only when `content_hash` differs (so formatting-only edits yield nothing). `source_diff` is a unified diff of exact `text` slices. Classification rules: endpoint removed, required parameter added, parameter became required, parameter type changed, request body became required or its schema changed, success (2xx) response removed, response schema changed → `breaking`. Schema property removed, property type changed, required property added, property became required, top-level type changed → `breaking`. Optional parameter/property added, new response code, endpoint/schema added, property no longer required → `non_breaking`. Parameter removed, non-2xx response removed, request body removed → `unknown`. Requirement added/removed/modified → `unknown`. Section/example changes → `documentation`. An endpoint or schema whose hash changed but whose contract did not (summary or description only) → `documentation`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_diff.py`

```python
from app.core.diff import diff_graphs
from app.core.models import ChangeType, Classification
from helpers import graph_of

API = """openapi: 3.0.0
paths:
  /things:
    get:
      summary: List things
{params}      responses:
        "200":
          description: ok
components:
  schemas:
    Thing:
      type: object
      required: [id]
      properties:
        id:
          type: string
"""

PARAM = """      parameters:
        - name: {name}
          in: query
          required: {required}
          schema:
            type: string
"""


def api(params: str = "", summary: str = "List things") -> dict[str, str]:
    return {"openapi.yaml": API.format(params=params).replace("List things", summary)}


def only(changes):
    assert len(changes) == 1, changes
    return changes[0]


def test_petstore_v1_to_v2_is_one_breaking_schema_change(v1, v2):
    change = only(diff_graphs(graph_of(v1), graph_of(v2)))
    assert change.key == "schema:Pet"
    assert change.change_type is ChangeType.MODIFIED
    assert change.classification is Classification.BREAKING
    assert any("property id type changed string -> integer" in r for r in change.reasons)
    assert "-          type: string" in change.source_diff
    assert "+          type: integer" in change.source_diff


def test_formatting_only_change_is_not_a_change(v1):
    edited = dict(v1)
    edited["openapi.yaml"] = v1["openapi.yaml"].replace("summary: List pets", "summary: List pets  # x")
    assert diff_graphs(graph_of(v1), graph_of(edited)) == []


def test_required_parameter_added_is_breaking():
    a, b = api(), api(PARAM.format(name="q", required="true"))
    c = only(diff_graphs(graph_of(a), graph_of(b)))
    assert c.classification is Classification.BREAKING
    assert "parameter q (query) added as required" in c.reasons


def test_optional_parameter_added_is_non_breaking():
    a, b = api(), api(PARAM.format(name="q", required="false"))
    assert only(diff_graphs(graph_of(a), graph_of(b))).classification is Classification.NON_BREAKING


def test_summary_only_change_is_documentation():
    a, b = api(), api(summary="Browse things")
    assert only(diff_graphs(graph_of(a), graph_of(b))).classification is Classification.DOCUMENTATION


def test_removed_endpoint_is_breaking():
    b = {"openapi.yaml": "openapi: 3.0.0\npaths: {}\ncomponents:\n  schemas: {}\n"}
    changes = {c.key: c for c in diff_graphs(graph_of(api()), graph_of(b))}
    assert changes["endpoint:GET /things"].change_type is ChangeType.REMOVED
    assert changes["endpoint:GET /things"].classification is Classification.BREAKING


def test_added_schema_property_required_vs_optional():
    base = api()["openapi.yaml"]
    optional = base.replace("          type: string\n", "          type: string\n        note:\n          type: string\n", 1)
    c = only(diff_graphs(graph_of({"openapi.yaml": base}), graph_of({"openapi.yaml": optional})))
    assert c.classification is Classification.NON_BREAKING


def test_requirement_change_is_unknown_not_breaking():
    a = {"a.md": "## A\nREQ-001: Clients MUST retry.\n"}
    b = {"a.md": "## A\nREQ-001: Clients SHOULD retry.\n"}
    c = only(diff_graphs(graph_of(a), graph_of(b)))
    assert c.key == "requirement:REQ-001"
    assert c.classification is Classification.UNKNOWN


def test_prose_change_is_documentation():
    a = {"a.md": "## A\nhello\n"}
    b = {"a.md": "## A\nhello there\n"}
    assert only(diff_graphs(graph_of(a), graph_of(b))).classification is Classification.DOCUMENTATION
```

- [ ] **Step 2: Run to verify it fails**

Run: `conda run -n SpecTrace pytest tests/test_diff.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.core.diff'`.

- [ ] **Step 3: Write the implementation** — `backend/app/core/diff.py`

```python
import difflib

from app.core.graph import Graph
from app.core.models import Change, ChangeType, Classification, Entity, EntityKind

_DOC_ONLY = ["no contract change detected; documentation or metadata only"]


def diff_graphs(a: Graph, b: Graph) -> list[Change]:
    changes = []
    for key in sorted(set(a.entities) | set(b.entities)):
        ea, eb = a.entities.get(key), b.entities.get(key)
        if ea is None:
            change_type, cls, reasons = ChangeType.ADDED, *_classify_added_removed(eb, added=True)
        elif eb is None:
            change_type, cls, reasons = ChangeType.REMOVED, *_classify_added_removed(ea, added=False)
        elif ea.content_hash != eb.content_hash:
            change_type, (cls, reasons) = ChangeType.MODIFIED, _classify_modified(ea, eb)
        else:
            continue
        ref = eb or ea
        changes.append(
            Change(
                key=key, kind=ref.kind, change_type=change_type, classification=cls,
                reasons=reasons, source_diff=_source_diff(ea, eb),
                before=ea.location if ea else None, after=eb.location if eb else None,
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
        return Classification.UNKNOWN, [f"requirement {verb}; effect not classified deterministically"]
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `conda run -n SpecTrace pytest tests/test_diff.py -v`
Expected: all pass.

- [ ] **Step 5: Commit** `feat: entity diff with deterministic change classification`

---

### Task 7: Impact engine with evidence paths

**Files:**
- Create: `backend/app/core/impact.py`
- Test: `backend/tests/test_impact.py`

**Interfaces:**
- Consumes: `Change`, `Edge`.
- Produces: `find_impacts(change: Change, edges_a: list[Edge], edges_b: list[Edge], max_depth: int = 3, max_expansions: int = 20_000) -> list[Impact]`. Walks edges backwards from `change.key` over the union of both versions' edges (version B wins on a duplicate `(source, target, relation)`). One best impact per impacted entity, chosen by (all edges confirmed, confidence, shorter path). `Impact.path[0]` is the edge touching the changed entity. `certainty` is `confirmed` only if every edge is `confirmed`. `confidence` is the product of edge confidences. `confirmed_breaking` is true only if `change.classification` is `breaking` **and** `certainty` is `confirmed`. Results sorted: confirmed first, then confidence descending, then key.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_impact.py`

```python
from app.core.diff import diff_graphs
from app.core.impact import find_impacts
from app.core.models import Label
from helpers import graph_of


def impacts_for(a_files, b_files, key, **kw):
    ga, gb = graph_of(a_files), graph_of(b_files)
    change = next(c for c in diff_graphs(ga, gb) if c.key == key)
    return find_impacts(change, ga.edges, gb.edges, **kw)


def by_label(impacts, label):
    return {i.impacted_key for i in impacts if i.certainty is label}


def test_pet_change_impact_sets(v1, v2):
    impacts = impacts_for(v1, v2, "schema:Pet")
    assert by_label(impacts, Label.CONFIRMED) == {
        "endpoint:GET /pets",
        "endpoint:POST /pets",
        "endpoint:GET /pets/{petId}",
        "section:docs/guide.md#listing-pets",
        "section:docs/guide.md#fetching-a-pet",
    }
    assert by_label(impacts, Label.INFERRED) == {
        "requirement:REQ-001",
        "example:docs/guide.md#fetching-a-pet:1",
    }


def test_unrelated_entities_are_not_reported(v1, v2):
    impacted = {i.impacted_key for i in impacts_for(v1, v2, "schema:Pet")}
    assert impacted.isdisjoint(
        {"endpoint:GET /owners", "schema:Owner", "schema:NewPet", "section:docs/guide.md#owners"}
    )


def test_confirmed_path_carries_line_evidence(v1, v2):
    imp = next(i for i in impacts_for(v1, v2, "schema:Pet") if i.impacted_key == "section:docs/guide.md#listing-pets")
    assert [e.target_key for e in imp.path] == ["schema:Pet", "endpoint:GET /pets"]
    assert all(e.label is Label.CONFIRMED for e in imp.path)
    assert all(e.evidence.line_start >= 1 for e in imp.path)
    assert imp.confidence == 1.0


def test_confirmed_breaking_requires_deterministic_rule_and_confirmed_path(v1, v2):
    for imp in impacts_for(v1, v2, "schema:Pet"):
        assert imp.confirmed_breaking == (imp.certainty is Label.CONFIRMED)
        if imp.certainty is Label.INFERRED:
            assert imp.confirmed_breaking is False


def test_inferred_confidence_is_edge_product(v1, v2):
    by_key = {i.impacted_key: i for i in impacts_for(v1, v2, "schema:Pet")}
    assert by_key["requirement:REQ-001"].confidence == 0.8
    assert by_key["example:docs/guide.md#fetching-a-pet:1"].confidence == 0.6


def test_depth_limit_downgrades_to_inferred_direct_edge(v1, v2):
    imp = next(
        i for i in impacts_for(v1, v2, "schema:Pet", max_depth=1)
        if i.impacted_key == "section:docs/guide.md#listing-pets"
    )
    assert imp.certainty is Label.INFERRED


def test_removed_endpoint_impacts_use_edges_from_old_version(v1):
    lines = v1["openapi.yaml"].splitlines()
    start = lines.index("  /pets/{petId}:")
    end = lines.index("  /owners:")
    v2 = dict(v1)
    v2["openapi.yaml"] = "\n".join(lines[:start] + lines[end:]) + "\n"
    impacts = impacts_for(v1, v2, "endpoint:GET /pets/{petId}")
    assert "section:docs/guide.md#fetching-a-pet" in by_label(impacts, Label.CONFIRMED)
```

- [ ] **Step 2: Run to verify it fails**

Run: `conda run -n SpecTrace pytest tests/test_impact.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.core.impact'`.

- [ ] **Step 3: Write the implementation** — `backend/app/core/impact.py`

```python
from collections import defaultdict
from math import prod

from app.core.models import Change, Classification, Edge, Impact, Label


def find_impacts(
    change: Change,
    edges_a: list[Edge],
    edges_b: list[Edge],
    max_depth: int = 3,
    max_expansions: int = 20_000,
) -> list[Impact]:
    merged: dict[tuple[str, str, str], Edge] = {}
    for e in [*edges_a, *edges_b]:
        merged[(e.source_key, e.target_key, e.relation)] = e
    incoming: dict[str, list[Edge]] = defaultdict(list)
    for e in merged.values():
        incoming[e.target_key].append(e)

    best: dict[str, tuple[tuple, tuple[Edge, ...]]] = {}
    stack: list[tuple[str, tuple[Edge, ...], frozenset[str]]] = [(change.key, (), frozenset({change.key}))]
    expansions = 0
    while stack:
        node, path, seen = stack.pop()
        if len(path) >= max_depth:
            continue
        for e in incoming.get(node, []):
            if e.source_key in seen:
                continue
            expansions += 1
            if expansions > max_expansions:
                stack.clear()
                break
            new_path = path + (e,)
            score = _score(new_path)
            if e.source_key not in best or score > best[e.source_key][0]:
                best[e.source_key] = (score, new_path)
            stack.append((e.source_key, new_path, seen | {e.source_key}))

    impacts = [_impact(change, key, path) for key, (_, path) in best.items()]
    impacts.sort(key=lambda i: (i.certainty is not Label.CONFIRMED, -i.confidence, i.impacted_key))
    return impacts


def _score(path: tuple[Edge, ...]) -> tuple:
    confirmed = all(e.label is Label.CONFIRMED for e in path)
    return (confirmed, prod(e.confidence for e in path), -len(path))


def _impact(change: Change, impacted_key: str, path: tuple[Edge, ...]) -> Impact:
    certainty = Label.CONFIRMED if all(e.label is Label.CONFIRMED for e in path) else Label.INFERRED
    hops = " -> ".join(f"{e.source_key} {e.relation} {e.target_key}" for e in reversed(path))
    return Impact(
        change_key=change.key,
        impacted_key=impacted_key,
        certainty=certainty,
        confidence=round(prod(e.confidence for e in path), 4),
        path=list(path),
        confirmed_breaking=change.classification is Classification.BREAKING and certainty is Label.CONFIRMED,
        summary=f"[{certainty.value}] {impacted_key} depends on {change.key} via: {hops}",
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `conda run -n SpecTrace pytest tests/test_impact.py -v`
Expected: all pass. If `test_pet_change_impact_sets` fails, print the impacts and compare to the hand-labeled sets in the test before touching code; the sets are the specification.

- [ ] **Step 5: Commit** `feat: evidence-path impact engine`

---

### Task 8: Pipeline, limits enforcement, question answering, regression scenarios

**Files:**
- Create: `backend/app/core/pipeline.py`
- Test: `backend/tests/test_pipeline.py`, `backend/tests/test_regression_scenarios.py`

**Interfaces:**
- Consumes: parsers, `build_graph`, `diff_graphs`, `find_impacts`, `Limits`, errors.
- Produces: `analyze(files_a: dict[str, str], files_b: dict[str, str], limits: Limits | None = None, max_depth: int = 3) -> AnalysisResult` with fields `changes: list[Change]`, `impacts: dict[str, list[Impact]]` (keyed by change key; only for `removed` and `modified` changes), `graph_a: Graph`, `graph_b: Graph`, `unsupported: list[str]`, `warnings: list[str]`, `stats: dict[str, int | float]`. `answer_question(result: AnalysisResult, question: str) -> QuestionAnswer(status: "answered" | "no_change" | "uncertain", matched: list[str], impacts: list[Impact], reason: str)`. Entity names match case-sensitively on word boundaries.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_pipeline.py`

```python
import pytest

from app.core.limits import Limits
from app.core.pipeline import analyze, answer_question
from app.errors import InputTooLarge, LimitExceeded, UnsupportedInput


def test_analyze_petstore(v1, v2):
    result = analyze(v1, v2)
    assert [c.key for c in result.changes] == ["schema:Pet"]
    assert len(result.impacts["schema:Pet"]) == 7
    assert result.stats["files_a"] == 2 and result.stats["changes"] == 1
    assert result.stats["elapsed_ms"] >= 0


def test_unsupported_files_are_reported_not_parsed(v1, v2):
    extra = {"logo.png": "binary", "notes.yaml": "name: not openapi\n"}
    result = analyze({**v1, **extra}, {**v2, **extra})
    assert any("logo.png" in u for u in result.unsupported)
    assert any("notes.yaml" in u for u in result.unsupported)


@pytest.mark.parametrize("name", ["../evil.md", "/etc/passwd.md", "C:/x.md", "a/../../b.md"])
def test_unsafe_paths_are_rejected(name):
    with pytest.raises(UnsupportedInput):
        analyze({name: "# x\n"}, {})


def test_file_size_limit():
    with pytest.raises(InputTooLarge):
        analyze({"a.md": "x" * 11}, {}, Limits(max_file_bytes=10))


def test_file_count_limit():
    files = {f"{i}.md": "# x\n" for i in range(3)}
    with pytest.raises(LimitExceeded):
        analyze(files, {}, Limits(max_files=2))


def test_question_answered_with_impacts(v1, v2):
    ans = answer_question(analyze(v1, v2), "What is impacted by the Pet change?")
    assert ans.status == "answered"
    assert ans.matched == ["schema:Pet"]
    assert len(ans.impacts) == 7


def test_question_about_unchanged_entity(v1, v2):
    ans = answer_question(analyze(v1, v2), "What about Owner?")
    assert ans.status == "no_change"
    assert ans.impacts == []


def test_unknown_subject_is_uncertain_not_fabricated(v1, v2):
    ans = answer_question(analyze(v1, v2), "How does billing break?")
    assert ans.status == "uncertain"
    assert ans.impacts == [] and ans.reason
```

`backend/tests/test_regression_scenarios.py` (maps to `Testing.md` section 3; scenario 5 belongs to the GitHub adapter in Plan 5):

```python
from app.core.models import Classification, Label
from app.core.pipeline import analyze, answer_question


def test_scenario_1_breaking_change_produces_expected_change_record(v1, v2):
    result = analyze(v1, v2)
    change = result.changes[0]
    assert (change.key, change.classification) == ("schema:Pet", Classification.BREAKING)
    assert change.before.line_start == change.after.line_start
    assert change.source_diff


def test_scenario_2_known_downstream_references_are_cited_correctly(v1, v2):
    result = analyze(v1, v2)
    files = v2
    checked = 0
    for impact in result.impacts["schema:Pet"]:
        for edge in impact.path:
            line = files[edge.evidence.file].splitlines()[edge.evidence.line_start - 1]
            if edge.relation == "uses_schema":
                assert "$ref" in line and edge.target_key.split(":", 1)[1] in line
            elif edge.relation == "mentions_endpoint":
                method, path = edge.target_key.split(":", 1)[1].split(" ", 1)
                assert method in line and path in line
            elif edge.relation == "mentions_name":
                assert f"`{edge.target_key.split(':', 1)[1]}`" in line
            checked += 1
    assert checked >= 7


def test_scenario_3_unrelated_components_are_never_confirmed_impacts(v1, v2):
    confirmed = {
        i.impacted_key
        for i in analyze(v1, v2).impacts["schema:Pet"]
        if i.certainty is Label.CONFIRMED
    }
    assert not confirmed & {"endpoint:GET /owners", "schema:Owner", "section:docs/guide.md#owners"}


def test_scenario_4_ambiguous_or_unsupported_questions_are_uncertain(v1, v2):
    result = analyze(v1, v2)
    assert answer_question(result, "Will the mobile app crash?").status == "uncertain"


def test_speculative_impact_is_never_presented_as_confirmed_breaking(v1, v2):
    for impacts in analyze(v1, v2).impacts.values():
        for imp in impacts:
            if imp.certainty is Label.INFERRED:
                assert not imp.confirmed_breaking
```

- [ ] **Step 2: Run to verify it fails**

Run: `conda run -n SpecTrace pytest tests/test_pipeline.py tests/test_regression_scenarios.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.core.pipeline'`.

- [ ] **Step 3: Write the implementation** — `backend/app/core/pipeline.py`

```python
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
            status="uncertain", matched=[], impacts=[],
            reason="The question does not name any known endpoint, schema, section or requirement.",
        )
    changed = [k for k in matched if k in result.impacts]
    if not changed:
        return QuestionAnswer(
            status="no_change", matched=matched, impacts=[],
            reason="The named entities did not change between the two versions.",
        )
    return QuestionAnswer(
        status="answered", matched=changed,
        impacts=[i for k in changed for i in result.impacts[k]],
        reason="Impacts are listed with evidence paths; inferred impacts are labeled as such.",
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `conda run -n SpecTrace pytest tests/test_pipeline.py tests/test_regression_scenarios.py -v`
Expected: all pass. If `len(impacts) == 7` fails, check the count against the Task 7 sets (5 confirmed + 2 inferred) before changing anything.

- [ ] **Step 5: Commit** `feat: analysis pipeline with limits and question answering`

---

### Task 9: Full verification and documentation sync

**Files:**
- Modify: `DOCS/State.md`, `DOCS/Decision.md`, `DOCS/Explain.md`, `DOCS/Design_graph.md`
- Do not touch: `DOCS/Testing.md`

- [ ] **Step 1: Run the whole suite with coverage and lint**

Run, in order: `python -m ruff format app tests`, `python -m ruff check --fix app tests`, `python -m ruff check app tests`, then `python -m pytest --cov=app -q` (all via `conda run -n SpecTrace --cwd backend`).
Expected: ruff clean; all tests pass after formatting. Some plan code exceeds 100 columns on purpose (readability in this document); the formatter wraps it. Fix remaining findings in code, not by disabling rules.

- [ ] **Step 2: Domain purity check**

Run: `grep -rnE "^(from|import) (fastapi|sqlalchemy|app\.(api|adapters))" backend/app/core` (use the Grep tool).
Expected: no matches.

- [ ] **Step 3: Update docs from what exists**

- `State.md`: mark the first vertical slice items that are actually implemented and tested, paste the real pytest summary line and coverage figure, list known gaps (no persistence, no HTTP routes beyond `/health`, no frontend, GitHub source, benchmark, deployment), refresh the skill graph with the superpowers skills actually loaded.
- `Decision.md`: add D-006 (deterministic-first engine, LLM off), D-007 (confirmed vs inferred labeling rule and thresholds 0.8/0.6/0.75), D-008 (ruamel round-trip loader for line numbers plus node/depth caps), D-009 (Docker Postgres locally, Supabase pooler in production), each with validation evidence from the test run.
- `Explain.md`: replace the planned implementation map with real paths for `backend/app/core/*`.
- `Design_graph.md`: add the core data-flow diagram (files → parsers → ParseResult → graph → diff → impact → AnalysisResult) and mark the DB, HTTP routes, and frontend nodes as planned.

- [ ] **Step 4: Commit** `docs: sync State, Decision, Explain and Design_graph with core engine`

---

## Self-Review

**Spec coverage (spec section → task):** 4 architecture layout → Tasks 1–8; 5 domain contract → Tasks 2, 5, 6, 7; labeling rule → Task 5 and tests in Tasks 5, 7, 8; abstention → Task 8; 7 error codes (`input_too_large`, `unsupported_input`, `parse_error`, `limit_exceeded`) → Tasks 1, 3, 8; 8 testing, unit and regression for `Testing.md` section 3 scenarios 1–4 → Tasks 3–8. Not in this plan, by design: persistence (spec 6), API routes, benchmark (spec 9), frontend, GitHub source and scenario 5, deployment, remaining error codes (`source_not_allowed`, `private_repo_not_authorized`, `run_timeout`). These belong to Plans 2 to 5.

**Spec delta:** the spec lists a bare-word mention heuristic at 0.5. This plan defers it, because it needs a full-text scan of every schema name and would add false positives before a benchmark exists. The spec is updated to match.

**Placeholder scan:** none; every code step contains the code.

**Type consistency:** `ParseResult`, `Graph`, `Change`, `Impact` and function signatures match across Tasks 2 to 8. `Edge.path[0]` is the edge touching the changed entity (Task 7), and Task 7's test asserts `[e.target_key ...] == ["schema:Pet", "endpoint:GET /pets"]` accordingly.

**Known risks to watch during execution:** (1) ruamel `lc.key()` on YAML merge keys (`<<`), which is not exercised by tests; (2) the `Impact` count of 7 depends on the sample files exactly as written; (3) a heading literally titled "Preamble" shares the slug of the synthetic pre-heading section.

**Review log (2026-10-16), flaws found and fixed in this revision:**
1. The conda env had no Python, so `conda run -n SpecTrace pytest` silently used `C:\Python314` and base Anaconda packages. Fixed: Python 3.13.16 installed in the env; all commands use `python -m`; Task 0 Step 3 asserts the interpreter path.
2. `pip freeze` in a conda env emits local `file:///` paths that break Render installs. Fixed: hand-pinned `requirements.txt` / `requirements-dev.txt`.
3. `str, Enum` triggers ruff UP042 on py311+. Fixed: `StrEnum`.
4. `limits: Limits = Limits()` triggers ruff B008. Fixed: `None` default.
5. ruamel's recursive composer can raise `RecursionError` on extreme nesting, which would surface as a 500. Fixed: mapped to `LimitExceeded`; test parametrized at depth 100 and 5000.
6. The health tests read a developer's `.env`. Fixed: `Settings(_env_file=None, ...)`.
7. The scenario-2 citation check verified only the HTTP method, so a wrong line containing "GET" would pass. Fixed: checks method and path.
8. Impact summary produced "confirmedly affected". Fixed wording.
9. Unsorted imports in `test_graph.py`, plus long lines. Fixed import order; Task 9 runs `ruff format` before `ruff check`.
10. Windows checkouts could convert samples to CRLF. Fixed: `.gitattributes` with `eol=lf`.

Verified during review: on ruamel 0.19.1 the 10^8-node alias bomb loads in 6 ms as shared objects and the node cap stops the walk at 200,001; `lc.key()` returns line info for YAML and JSON input.
