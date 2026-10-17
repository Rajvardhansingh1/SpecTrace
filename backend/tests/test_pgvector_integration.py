"""Runs against a real Postgres with pgvector (set SPECTRACE_TEST_DATABASE_URL).

Every run these tests create is deleted afterwards, which also deletes its chunks.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.adapters.llm import AI, HashingEmbedder, TestChat
from app.adapters.store import ChunkStore, RunStore, make_engine
from app.config import Settings
from app.core.chunking import Chunk
from app.main import create_app

URL = os.environ.get("SPECTRACE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="SPECTRACE_TEST_DATABASE_URL not set")

OWNER = {"X-Owner-Token": "pgvector-test-owner-0123456789"}
OTHER = {"X-Owner-Token": "pgvector-other-owner-9876543210"}


def settings() -> Settings:
    return Settings(_env_file=None, database_url=URL)


@pytest.fixture
def store():
    runs = RunStore(make_engine(settings().database_url))
    before = {r.id for r in runs.list(limit=1000)}
    yield runs
    for row in runs.list(limit=1000):
        if row.id not in before:
            runs.delete(row.id)


def chunk(key, text, ordinal=0):
    return Chunk(key, "b", "section", key, "f.md", 1, 2, ordinal, text)


def test_the_database_has_pgvector_and_the_chunk_table(store):
    assert store.dialect == "postgresql" and store.has_chunk_table()


def test_vectors_round_trip_and_the_database_ranks_by_cosine_similarity(store):
    run = store.create("a", "b", {"a.md": "x"}, {"a.md": "y"}, "owner")
    chunks = ChunkStore(store)
    items = [chunk("near", "n"), chunk("far", "f"), chunk("opposite", "o")]
    vectors = {
        items[0].text_hash: [1.0, 0.1, 0.0, 0.0],
        items[1].text_hash: [0.0, 1.0, 0.0, 0.0],
        items[2].text_hash: [-1.0, 0.0, 0.0, 0.0],
    }
    chunks.replace(run.id, items, vectors, "model-x")

    loaded = {c.chunk.key: c for c in chunks.load(run.id)}
    assert loaded["near"].embedding == [1.0, 0.1, 0.0, 0.0] and loaded["near"].model == "model-x"

    ranked = chunks.similar(run.id, [1.0, 0.0, 0.0, 0.0], "model-x", k=3)
    keys = [next(c.chunk.key for c in loaded.values() if c.id == cid) for cid, _ in ranked]
    assert keys == ["near", "far", "opposite"]
    assert ranked[0][1] == pytest.approx(0.995, abs=0.01) and ranked[2][1] == pytest.approx(-1.0)
    assert len(chunks.similar(run.id, [1.0, 0.0, 0.0, 0.0], "model-x", k=1)) == 1


def test_similarity_only_considers_the_current_embedding_model(store):
    run = store.create("a", "b", {"a.md": "x"}, {"a.md": "y"}, "owner")
    chunks = ChunkStore(store)
    item = chunk("only", "t")
    chunks.replace(run.id, [item], {item.text_hash: [1.0, 0.0]}, "old-model")
    assert chunks.similar(run.id, [1.0, 0.0], "new-model") == []
    assert len(chunks.similar(run.id, [1.0, 0.0], "old-model")) == 1


def test_chunks_without_vectors_are_stored_and_skipped_by_similarity(store):
    run = store.create("a", "b", {"a.md": "x"}, {"a.md": "y"}, "owner")
    chunks = ChunkStore(store)
    chunks.replace(run.id, [chunk("plain", "t")])
    assert chunks.load(run.id)[0].embedding is None
    assert chunks.similar(run.id, [1.0, 0.0], "m") == []


def test_deleting_a_run_deletes_its_chunks(store):
    run = store.create("a", "b", {"a.md": "x"}, {"a.md": "y"}, "owner")
    chunks = ChunkStore(store)
    chunks.replace(run.id, [chunk("k", "t")])
    store.delete(run.id)
    assert chunks.load(run.id) == []


def test_the_whole_question_flow_works_on_postgres_with_owner_scoping(v1, v2):
    ai = AI(TestChat(), HashingEmbedder(), "test", "hashing", [])
    c = TestClient(create_app(settings(), ai=ai), headers=OWNER, raise_server_exceptions=False)
    body = {"files_a": v1, "files_b": v2, "label_a": "v1", "label_b": "v2"}
    rid = c.post("/v1/runs", json=body).json()["id"]
    try:
        out = c.post(f"/v1/runs/{rid}/ask", json={"question": "What breaks if Pet changes?"}).json()
        assert (
            out["generated"] is True and out["citations"] and out["retrieval"]["semantic"] is True
        )
        narrative = c.post(f"/v1/runs/{rid}/narrative", json={}).json()
        assert narrative["changes"]["status"] == "answered"
        assert c.get(f"/v1/runs/{rid}").json()["result"]["narrative"] == narrative
        assert c.get(f"/v1/runs/{rid}", headers=OTHER).status_code == 404
        assert [r["id"] for r in c.get("/v1/runs", headers=OTHER).json()["runs"]] == []
    finally:
        c.app.state.store.delete(rid)
