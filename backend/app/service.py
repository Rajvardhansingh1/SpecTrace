"""The application layer for the language-model features.

It connects the pieces: the deterministic analysis, chunking, embeddings, retrieval, the model and
the stores. Every step can be missing and the service degrades instead of failing:

* no model configured: questions are answered by name matching, as before;
* no embedder: retrieval is keyword and graph based;
* the embedding service fails: the question is still answered from keywords.
"""

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from app.adapters.llm import AI
from app.adapters.store import ChunkStore, RunRow, RunStore, StoredChunk
from app.config import Settings
from app.core.chunking import Chunk, chunk_entities
from app.core.llm import CallBudget
from app.core.pipeline import AnalysisResult, analyze
from app.core.pipeline import answer_question as name_match_answer
from app.core.rag import (
    Generated,
    answer_question,
    build_context,
    summarize_changes,
    summarize_version,
)
from app.core.retrieval import cosine, retrieve
from app.errors import LLMUnavailable, SpecTraceError

log = logging.getLogger("spectrace")
TOP_K = 8


def _part(out: Generated) -> dict[str, Any]:
    return {
        "status": out.status,
        "text": out.text,
        "citations": [asdict(c) for c in out.citations],
        "warnings": out.warnings,
        "truncated": out.truncated,
        "model": out.model,
    }


class AIService:
    def __init__(
        self,
        settings: Settings,
        ai: AI,
        runs: RunStore,
        chunks: ChunkStore,
        budget: CallBudget,
    ):
        self._settings = settings
        self._ai = ai
        self._runs = runs
        self._chunks = chunks
        self._budget = budget

    # ------------------------------------------------------------------ what is available
    def capabilities(self) -> dict[str, Any]:
        chat, embedder = self._ai.chat, self._ai.embedder
        return {
            "llm": {"enabled": chat is not None, "model": chat.name if chat else None},
            "embeddings": {
                "enabled": embedder is not None,
                "model": embedder.name if embedder else None,
            },
            # Who receives document text. Empty means nothing leaves this server.
            "sends_documents_to": self._ai.recipients,
        }

    @property
    def has_llm(self) -> bool:
        return self._ai.chat is not None

    def _require_llm(self):
        if self._ai.chat is None:
            raise LLMUnavailable("No language model is configured on this server.")
        return self._ai.chat

    # ------------------------------------------------------------------------- indexing
    def _index(self, row: RunRow, owner: str, analysis: AnalysisResult):
        """Stored chunks for the run, embedding them once. Returns (stored chunks, vectors used)."""
        embedder = self._ai.embedder
        use_db = self._runs.has_chunk_table()
        stored = self._chunks.load(row.id) if use_db else []
        wanted_model = embedder.name if embedder else None
        complete = bool(stored) and (
            embedder is None or all(s.model == wanted_model for s in stored if s.embedding)
        )
        needs_vectors = embedder is not None and not any(s.embedding for s in stored)
        if stored and complete and not needs_vectors:
            return stored, bool(embedder)

        chunks: list[Chunk] = [
            *chunk_entities(analysis.graph_a.entities, "a"),
            *chunk_entities(analysis.graph_b.entities, "b"),
        ]
        vectors: dict[str, list[float]] = {}
        if embedder is not None:
            unique = {c.text_hash: c.embed_text for c in chunks}
            if len(unique) > self._settings.embedding_max_chunks_per_run:
                log.warning("too many chunks to embed (%s)", len(unique))
            else:
                try:
                    self._budget.charge(owner)
                    hashes = list(unique)
                    vectors = dict(
                        zip(hashes, embedder.embed([unique[h] for h in hashes]), strict=True)
                    )
                except SpecTraceError as exc:
                    log.warning("embedding failed code=%s", exc.code)
        if use_db:
            self._chunks.replace(row.id, chunks, vectors, wanted_model)
            return self._chunks.load(row.id), bool(vectors)
        # No chunk table (migration not applied): work in memory for this request only.
        return (
            [
                StoredChunk(i, c, vectors.get(c.text_hash), wanted_model if vectors else None)
                for i, c in enumerate(chunks)
            ],
            bool(vectors),
        )

    # ------------------------------------------------------------------------ summaries
    def narrative(self, row: RunRow, owner: str, refresh: bool = False) -> dict[str, Any]:
        chat = self._require_llm()
        existing = (row.result or {}).get("narrative")
        if existing and not refresh:
            return existing
        self._budget.charge(owner, 3)
        analysis = analyze(row.files_a, row.files_b)
        s = self._settings
        common = {
            "max_chars": s.llm_context_chars,
            "max_tokens": s.llm_max_output_tokens,
            "on_retry": lambda: self._budget.charge(owner),
        }
        parts = {
            "version_a": _part(
                summarize_version(
                    chat, row.label_a, chunk_entities(analysis.graph_a.entities, "a"), **common
                )
            ),
            "version_b": _part(
                summarize_version(
                    chat, row.label_b, chunk_entities(analysis.graph_b.entities, "b"), **common
                )
            ),
            "changes": _part(
                summarize_changes(
                    chat, row.label_a, row.label_b, analysis.changes, analysis.impacts, **common
                )
            ),
        }
        # A router can send each call to a different model, so name every model that wrote a part.
        used = sorted({p["model"] for p in parts.values() if p["model"]}) or [chat.name]
        narrative = {
            **parts,
            "model": ", ".join(used),
            "sent_to": self._ai.recipients,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self._runs.set_narrative(row.id, narrative)
        return narrative

    # ---------------------------------------------------------------------------- ask
    def ask(self, row: RunRow, owner: str, question: str) -> dict[str, Any]:
        analysis = analyze(row.files_a, row.files_b)
        base = name_match_answer(analysis, question)
        response: dict[str, Any] = {
            "status": base.status,
            "matched": base.matched,
            "impacts": [i.model_dump(mode="json") for i in base.impacts],
            "reason": base.reason,
            "answer": None,
            "citations": [],
            "generated": False,
            "model": None,
            "warnings": [],
            "truncated": False,
            "retrieval": None,
        }
        chat = self._ai.chat
        if chat is None:
            return response

        stored, vectors_used = self._index(row, owner, analysis)
        chunk_list = [s.chunk for s in stored]
        embedder = self._ai.embedder
        similarities: dict[int, float] = {}
        if embedder is not None and vectors_used:
            try:
                self._budget.charge(owner)
                query = embedder.embed([question])[0]
                index_of = {s.id: i for i, s in enumerate(stored)}
                if self._runs.has_chunk_table():
                    for chunk_id, sim in self._chunks.similar(row.id, query, embedder.name, 20):
                        similarities[index_of[chunk_id]] = sim
                else:
                    for i, item in enumerate(stored):
                        if item.embedding:
                            similarities[i] = cosine(query, item.embedding)
            except SpecTraceError as exc:
                log.warning("query embedding failed code=%s", exc.code)
                response["warnings"].append("Semantic search was unavailable; keywords were used.")
        hits = retrieve(
            question,
            chunk_list,
            similarities=similarities or None,
            min_similarity=embedder.min_similarity if embedder else 0.25,
            top_k=TOP_K,
        )
        items, truncated = build_context(
            question, analysis, hits, max_chars=self._settings.llm_context_chars
        )
        self._budget.charge(owner)
        out = answer_question(
            chat,
            question,
            items,
            truncated=truncated,
            max_tokens=self._settings.llm_max_output_tokens,
        )
        response.update(
            status=out.status,
            answer=out.text,
            citations=[asdict(c) for c in out.citations],
            generated=True,
            model=out.model or chat.name,
            warnings=[*response["warnings"], *out.warnings],
            truncated=out.truncated,
            retrieval={
                "chunks": len(chunk_list),
                "semantic": bool(similarities),
                "items": len(items),
            },
        )
        return response
