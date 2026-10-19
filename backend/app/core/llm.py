"""Interfaces for the language model and the embedder, and the budget that guards them.

Nothing here talks to the network. Adapters live in `app.adapters`.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.errors import BudgetExceeded


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" or "user"
    content: str


@dataclass(frozen=True)
class Completion:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    #: The model that actually answered. A router such as openrouter/free picks one per call.
    model: str | None = None
    finish_reason: str | None = None


class ChatModel(Protocol):
    name: str

    def complete(
        self, messages: list[ChatMessage], *, max_tokens: int, temperature: float = 0.1
    ) -> Completion: ...


class Embedder(Protocol):
    name: str
    #: Cosine similarity below this is treated as unrelated; it differs a lot between embedders.
    min_similarity: float

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class CallBudget:
    """Bounds paid calls: per owner per hour and per process per day. In memory, per process."""

    def __init__(
        self,
        per_owner_per_hour: int,
        per_day: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._per_owner = per_owner_per_hour
        self._per_day = per_day
        self._clock = clock
        self._owners: dict[str, list[float]] = {}
        self._day: list[float] = []
        self._lock = threading.Lock()

    def charge(self, owner: str, calls: int = 1) -> None:
        now = self._clock()
        with self._lock:
            self._day = [t for t in self._day if t > now - 86_400]
            hits = [t for t in self._owners.get(owner, []) if t > now - 3_600]
            if len(self._day) + calls > self._per_day:
                raise BudgetExceeded("The daily limit for language-model calls has been reached.")
            if len(hits) + calls > self._per_owner:
                raise BudgetExceeded("Too many language-model requests this hour. Try again later.")
            hits.extend([now] * calls)
            self._owners[owner] = hits
            self._day.extend([now] * calls)
            if len(self._owners) > 10_000:  # bound memory against many distinct owners
                self._owners.pop(next(iter(self._owners)))
