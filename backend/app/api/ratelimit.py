import threading
import time
from collections import deque
from collections.abc import Callable


class SlidingWindowLimiter:
    """Allows at most `limit` hits per `window` seconds for each key.

    State is in process memory: it resets on restart and is not shared between workers.
    The number of tracked keys is capped so a flood of distinct clients cannot grow it forever.
    """

    def __init__(
        self,
        limit: int,
        window: float = 60.0,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.limit = limit
        self.window = window
        self.max_keys = max_keys
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Return (allowed, seconds to wait before retrying)."""
        now = self._clock()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= self.max_keys:
                    self._evict(now)
                hits = self._hits[key] = deque()
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, max(1, int(hits[0] + self.window - now) + 1)
            hits.append(now)
            return True, 0

    def _evict(self, now: float) -> None:
        stale = [k for k, h in self._hits.items() if not h or h[-1] <= now - self.window]
        for k in stale:
            del self._hits[k]
        if len(self._hits) >= self.max_keys:
            # Everything is active: drop the oldest-inserted key rather than refuse new clients.
            del self._hits[next(iter(self._hits))]
