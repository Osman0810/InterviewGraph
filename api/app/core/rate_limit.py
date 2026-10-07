"""Small in-process safety valve; use a shared limiter at multi-instance scale."""

from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class InMemoryRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window = window_seconds
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        with self._lock:
            now = monotonic()
            entries = self._requests[key]
            while entries and entries[0] <= now - self._window:
                entries.popleft()
            if len(entries) >= self._limit:
                retry_after = max(1, int(self._window - (now - entries[0])) + 1)
                return False, retry_after
            entries.append(now)
            return True, 0
