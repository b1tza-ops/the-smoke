from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol


class RateLimitExceededError(Exception):
    """Raised when an authentication action is attempted too often."""


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter(Protocol):
    def check(self, key, now=None):
        """Return a RateLimitDecision for the supplied action key."""


class NullRateLimiter:
    """Default hook used until a deployment provides shared storage."""

    def check(self, key, now=None):
        return RateLimitDecision(allowed=True)


class InMemoryRateLimiter:
    """Small local limiter suitable for tests and one-process development."""

    def __init__(
        self,
        limit=5,
        window_seconds=15 * 60,
    ):
        if limit <= 0:
            raise ValueError(
                "Rate limit must be positive."
            )

        if window_seconds <= 0:
            raise ValueError(
                "Rate-limit window must be positive."
            )

        self.limit = limit
        self.window = timedelta(
            seconds=window_seconds,
        )
        self._attempts = defaultdict(deque)

    def check(self, key, now=None):
        now = _normalise_now(now)
        attempts = self._attempts[str(key)]
        cutoff = now - self.window

        while attempts and attempts[0] <= cutoff:
            attempts.popleft()

        if len(attempts) >= self.limit:
            retry_after = max(
                1,
                int(
                    (
                        attempts[0]
                        + self.window
                        - now
                    ).total_seconds()
                ),
            )

            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=retry_after,
            )

        attempts.append(now)
        return RateLimitDecision(allowed=True)


def enforce_rate_limit(limiter, key, now=None):
    limiter = limiter or NullRateLimiter()
    decision = limiter.check(key, now=now)

    if not decision.allowed:
        raise RateLimitExceededError(
            "Too many attempts. Try again later."
        )

    return decision


def _normalise_now(now=None):
    if now is None:
        return datetime.now(timezone.utc)

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    return now.astimezone(timezone.utc)
