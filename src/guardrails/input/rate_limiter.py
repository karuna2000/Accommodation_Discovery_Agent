import time
from collections import defaultdict


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int = 100, window_seconds: float = 60.0):
        self._max_requests = max_requests
        self._window = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets[key]
        cutoff = now - self._window
        self._buckets[key] = [t for t in bucket if t > cutoff]
        if len(self._buckets[key]) >= self._max_requests:
            return False
        self._buckets[key].append(now)
        return True
