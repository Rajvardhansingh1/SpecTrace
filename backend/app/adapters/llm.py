"""Adapters for the language model and the embedder.

The chat and embedding adapters speak the OpenAI-compatible HTTP protocol, which OpenRouter, Groq
and Jina all offer, so a provider is a base URL, a key and a model name.

Failure behavior is fixed: a bounded number of retries for rate limits, server errors and
timeouts, then a stable error. Error text never includes the request, the response body or the key,
because a provider can echo the prompt, which holds the submitted documents.
"""

import hashlib
import json
import logging
import math
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.core.llm import ChatMessage, ChatModel, Completion, Embedder
from app.errors import LLMBadOutput, LLMRateLimited, LLMTimeout, LLMUnavailable

log = logging.getLogger("spectrace")

# Hosted services that always need a key. Without one the feature is treated as not configured,
# so a copied .env.example with the keys still blank leaves the app working without a model.
KEY_REQUIRED = {"openrouter", "groq", "jina"}
PRESET_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "jina": "https://api.jina.ai/v1",
}
PRESET_LABELS = {"openrouter": "OpenRouter", "groq": "Groq", "jina": "Jina AI"}
MAX_EMBED_CHARS = 8_000
MAX_RETRY_WAIT_SECONDS = 5.0


def _post(
    client: httpx.Client,
    url: str,
    api_key: str | None,
    payload: dict,
    *,
    timeout: float,
    retries: int,
    sleep: Callable[[float], None],
) -> dict:
    headers = {"Content-Type": "application/json", "X-Title": "SpecTrace"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    last: Exception | None = None
    for attempt in range(retries + 1):
        wait = min(0.5 * 2**attempt, MAX_RETRY_WAIT_SECONDS) * (0.75 + random.random() / 2)
        try:
            response = client.post(url, headers=headers, json=payload, timeout=timeout)
        except httpx.TimeoutException as exc:
            last = LLMTimeout("The language model service took too long to answer.")
            last.__cause__ = exc
        except httpx.HTTPError as exc:
            last = LLMUnavailable("The language model service could not be reached.")
            last.__cause__ = exc
        else:
            code = response.status_code
            if code == 200:
                try:
                    body = response.json()
                except ValueError as exc:
                    raise LLMBadOutput(
                        "The language model service returned unreadable data."
                    ) from exc
                if not isinstance(body, dict):
                    raise LLMBadOutput("The language model service returned unreadable data.")
                return body
            if code in (401, 403):
                raise LLMUnavailable("The language model service rejected the API key.")
            if code == 429:
                last = LLMRateLimited("The language model service is rate limiting requests.")
                retry_after = response.headers.get("retry-after", "")
                if retry_after.replace(".", "", 1).isdigit():
                    wait = min(float(retry_after), MAX_RETRY_WAIT_SECONDS)
            elif code >= 500:
                last = LLMUnavailable(f"The language model service failed (HTTP {code}).")
            else:
                raise LLMUnavailable(
                    f"The language model service rejected the request (HTTP {code})."
                )
        if attempt < retries:
            sleep(wait)
    assert last is not None
    raise last


class OpenAICompatChat:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
        *,
        timeout: float = 60.0,
        retries: int = 2,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.name = model
        self._url = f"{base_url}/chat/completions"
        self._key = api_key
        self._timeout = timeout
        self._retries = retries
        self._client = client or httpx.Client()
        self._sleep = sleep

    def complete(
        self, messages: list[ChatMessage], *, max_tokens: int, temperature: float = 0.1
    ) -> Completion:
        payload = {
            "model": self.name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        body = _post(
            self._client,
            self._url,
            self._key,
            payload,
            timeout=self._timeout,
            retries=self._retries,
            sleep=self._sleep,
        )
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMBadOutput("The language model returned no answer.") from exc
        if not isinstance(text, str) or not text.strip():
            raise LLMBadOutput("The language model returned an empty answer.")
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        return Completion(text, usage.get("prompt_tokens"), usage.get("completion_tokens"))


class OpenAICompatEmbedder:
    min_similarity = 0.25

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
        *,
        batch_size: int = 64,
        timeout: float = 60.0,
        retries: int = 2,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.name = model
        self._url = f"{base_url}/embeddings"
        self._key = api_key
        self._batch = max(1, batch_size)
        self._timeout = timeout
        self._retries = retries
        self._client = client or httpx.Client()
        self._sleep = sleep

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), self._batch):
            batch = [t[:MAX_EMBED_CHARS] or " " for t in texts[start : start + self._batch]]
            body = _post(
                self._client,
                self._url,
                self._key,
                {"model": self.name, "input": batch},
                timeout=self._timeout,
                retries=self._retries,
                sleep=self._sleep,
            )
            out.extend(self._vectors(body, len(batch)))
        dims = {len(v) for v in out}
        if len(dims) > 1:
            raise LLMBadOutput("The embedding service returned vectors of different sizes.")
        return out

    @staticmethod
    def _vectors(body: dict, expected: int) -> list[list[float]]:
        data = body.get("data")
        if not isinstance(data, list) or len(data) != expected:
            raise LLMBadOutput("The embedding service returned the wrong number of vectors.")
        ordered = sorted(
            data, key=lambda item: item.get("index", 0) if isinstance(item, dict) else 0
        )
        vectors = []
        for item in ordered:
            vec = item.get("embedding") if isinstance(item, dict) else None
            if (
                not isinstance(vec, list)
                or not vec
                or not all(isinstance(x, int | float) and math.isfinite(x) for x in vec)
            ):
                raise LLMBadOutput("The embedding service returned an invalid vector.")
            vectors.append([float(x) for x in vec])
        return vectors


class HashingEmbedder:
    """A local bag-of-words embedder: no model, no key, no network.

    Weaker than a trained model (it matches shared words, not meaning), but deterministic, instant
    and private. It is the fallback and the test embedder.
    """

    min_similarity = 0.08

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.name = f"hashing-{dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        words = re.findall(r"[a-z0-9_]+", text.lower())
        grams = words + [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
        for gram in grams:
            digest = hashlib.blake2b(gram.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec] if norm else vec


class FastEmbedEmbedder:
    """Local ONNX embeddings. Needs `pip install fastembed`; about a gigabyte of memory at peak."""

    min_similarity = 0.3

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5"):
        try:
            from fastembed import TextEmbedding  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on an optional package
            raise LLMUnavailable("fastembed is not installed on this server.") from exc
        self.name = model
        self._model = TextEmbedding(model_name=model)  # pragma: no cover

    def embed(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover
        return [
            list(map(float, v)) for v in self._model.embed([t[:MAX_EMBED_CHARS] for t in texts])
        ]


class TestChat:
    """A deterministic stand-in for tests and demos. It answers from the prompt, never from the web.

    It cites the first items of the context it is given, so the whole pipeline (retrieval, prompt,
    citation checking, display) can be exercised without a provider or a key.
    """

    __test__ = False  # not a pytest class
    name = "test-model"

    def complete(
        self, messages: list[ChatMessage], *, max_tokens: int, temperature: float = 0.1
    ) -> Completion:
        system = next((m.content for m in messages if m.role == "system"), "")
        user = next((m.content for m in messages if m.role == "user"), "")
        ids = re.findall(r"^\[(C\d+)\]", user, re.M)
        task = re.search(r"TASK:(\w+)", system)
        kind = task.group(1) if task else "answer"
        cited = ids[:2]
        refs = " ".join(f"[{i}]" for i in cited)
        if kind == "answer":
            body = (
                {
                    "answer": "The documents do not contain enough to answer.",
                    "citations": [],
                    "abstain": True,
                }
                if not cited
                else {
                    "answer": f"Test answer based on the supplied context {refs}.",
                    "citations": cited,
                    "abstain": False,
                }
            )
        else:
            body = {"summary": f"Test summary {refs}".strip(), "citations": cited}
        return Completion(json.dumps(body), 0, 0)


@dataclass(frozen=True)
class AI:
    """What the application may use. Either part can be missing."""

    chat: ChatModel | None
    embedder: Embedder | None
    llm_provider: str
    embedding_provider: str
    #: Names who receives document text, or None when nothing leaves this server.
    recipients: list[str]


def _label(provider: str, base_url: str | None) -> str:
    if provider in PRESET_LABELS:
        return PRESET_LABELS[provider]
    return urlparse(base_url or "").hostname or "the configured provider"


def _secret(value) -> str | None:
    text = value.get_secret_value() if value else ""
    return text or None


def build_ai(settings: Settings, client: httpx.Client | None = None) -> AI:
    chat: ChatModel | None = None
    embedder: Embedder | None = None
    recipients: list[str] = []

    provider = settings.llm_provider
    if provider == "test":
        chat = TestChat()
    elif provider != "none":
        key = _secret(settings.llm_api_key)
        base = settings.llm_base_url or PRESET_URLS.get(provider)
        if provider in KEY_REQUIRED and not key:
            log.warning("llm_provider=%s has no API key, so the language model is off", provider)
        else:
            if not base or not settings.llm_model:
                raise LLMUnavailable("The language model needs a base URL and a model name.")
            chat = OpenAICompatChat(
                base,
                key,
                settings.llm_model,
                timeout=settings.llm_timeout_seconds,
                retries=settings.llm_max_retries,
                client=client,
            )
            recipients.append(_label(provider, base))

    emb = settings.embedding_provider
    if emb == "hashing":
        embedder = HashingEmbedder()
    elif emb == "fastembed":
        embedder = FastEmbedEmbedder(settings.embedding_model or "BAAI/bge-small-en-v1.5")
    elif emb != "none":
        # OpenRouter serves both, so one key can cover chat and embeddings.
        key = _secret(settings.embedding_api_key) or (
            _secret(settings.llm_api_key) if provider == emb == "openrouter" else None
        )
        base = settings.embedding_base_url or PRESET_URLS.get(emb)
        if emb in KEY_REQUIRED and not key:
            log.warning("embedding_provider=%s has no API key, so embeddings are off", emb)
        else:
            if not base or not settings.embedding_model:
                raise LLMUnavailable("The embedding service needs a base URL and a model name.")
            embedder = OpenAICompatEmbedder(
                base,
                key,
                settings.embedding_model,
                batch_size=settings.embedding_batch_size,
                timeout=settings.llm_timeout_seconds,
                retries=settings.llm_max_retries,
                client=client,
            )
            label = _label(emb, base)
            if label not in recipients:
                recipients.append(label)

    return AI(chat, embedder, provider, emb, recipients)
