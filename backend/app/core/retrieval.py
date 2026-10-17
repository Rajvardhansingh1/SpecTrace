"""Hybrid retrieval: keyword ranking (BM25) fused with vector similarity.

Keyword ranking finds exact names, paths and identifiers that embeddings blur. Vector similarity
finds passages that say the same thing in other words. Reciprocal rank fusion combines the two
rankings without needing their scores to be comparable.
"""

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.chunking import Chunk

_TOKEN = re.compile(r"[a-z0-9_]+")
_STOP = frozenset(
    "a an and are as at be by for from has have how if in is it its of on or that the this to was "
    "were what when where which who why will with do does did can could should would about "
    "between changed change changes".split()
)
RRF_K = 60


def tokenize(text: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)  # petId -> pet Id
    words = _TOKEN.findall(spaced.lower())
    return [w for w in words if w not in _STOP and len(w) > 1]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class BM25:
    def __init__(self, documents: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self._docs = [Counter(d) for d in documents]
        self._lengths = [len(d) for d in documents]
        self._avg = (sum(self._lengths) / len(documents)) if documents else 0.0
        self._k1, self._b = k1, b
        df: Counter[str] = Counter()
        for doc in self._docs:
            df.update(doc.keys())
        n = len(documents)
        self._idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for doc, length in zip(self._docs, self._lengths, strict=True):
            score = 0.0
            for term in set(query):
                freq = doc.get(term, 0)
                if freq:
                    norm = freq + self._k1 * (1 - self._b + self._b * length / (self._avg or 1))
                    score += self._idf[term] * freq * (self._k1 + 1) / norm
            out.append(score)
        return out


@dataclass(frozen=True)
class Retrieved:
    chunk: Chunk
    score: float
    via: str  # "keyword", "vector" or "both"
    similarity: float | None


def retrieve(
    question: str,
    chunks: list[Chunk],
    *,
    vectors: dict[str, list[float]] | None = None,
    query_vector: list[float] | None = None,
    similarities: dict[int, float] | None = None,
    min_similarity: float = 0.25,
    top_k: int = 8,
) -> list[Retrieved]:
    """Best chunks for the question.

    Similarities come either from `vectors` (a chunk's text_hash to its embedding) and
    `query_vector`, computed here, or ready-made by chunk index in `similarities`, for example
    from a pgvector query.
    """
    if not chunks:
        return []
    keyword = BM25([tokenize(c.embed_text) for c in chunks]).scores(tokenize(question))
    by_keyword = [
        i for i in sorted(range(len(chunks)), key=lambda i: -keyword[i]) if keyword[i] > 0
    ]

    sims: dict[int, float] = dict(similarities or {})
    if not sims and vectors and query_vector:
        for i, chunk in enumerate(chunks):
            vec = vectors.get(chunk.text_hash)
            if vec is not None:
                sims[i] = cosine(query_vector, vec)
    by_vector = [i for i in sorted(sims, key=lambda i: -sims[i]) if sims[i] >= min_similarity]

    fused: dict[int, float] = {}
    for ranking in (by_keyword, by_vector):
        for rank, i in enumerate(ranking):
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)

    ordered = sorted(fused, key=lambda i: (-fused[i], chunks[i].key, chunks[i].ordinal))
    result = []
    for i in ordered[:top_k]:
        in_kw, in_vec = i in by_keyword, i in by_vector
        via = "both" if in_kw and in_vec else "keyword" if in_kw else "vector"
        result.append(Retrieved(chunks[i], round(fused[i], 5), via, sims.get(i)))
    return result
