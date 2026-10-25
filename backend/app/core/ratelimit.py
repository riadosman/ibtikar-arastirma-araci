"""Sliding one-minute windows kept in process memory (one backend process is supported)."""

import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    def __init__(self, window_seconds=60, max_keys=10_000):
        self.window, self.max_keys = window_seconds, max_keys
        self.hits = defaultdict(deque)
        self.lock = Lock()

    def allow(self, key, limit):
        current = time.monotonic()
        with self.lock:
            queue = self.hits[key]
            while queue and queue[0] < current - self.window:
                queue.popleft()
            if len(queue) >= limit:
                return False
            queue.append(current)
            if len(self.hits) > self.max_keys:
                for stale in [k for k, v in self.hits.items() if not v or v[-1] < current - self.window]:
                    self.hits.pop(stale, None)
            return True

    def clear(self):
        with self.lock:
            self.hits.clear()


limiter = RateLimiter()
