from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class FixedWindowRateLimiter:
    """Small process-local limiter for sensitive POST routes."""

    def __init__(self, clock=monotonic):
        self._clock = clock
        self._events = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key, limit, window_seconds):
        now = self._clock()
        cutoff = now - window_seconds

        with self._lock:
            events = self._events[key]

            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= limit:
                return False

            events.append(now)
            return True

    def clear(self):
        with self._lock:
            self._events.clear()
