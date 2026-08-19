import asyncio
import math
import time
from collections import deque
from dataclasses import dataclass

from cachetools import TTLCache


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0


class InMemoryRateLimiter:
    """A bounded, per-process fixed-window rate limiter."""

    def __init__(self, requests: int, window_seconds: int, max_clients: int = 10_000):
        self._limit = requests
        self._window = window_seconds
        self._requests: TTLCache[str, deque[float]] = TTLCache(
            maxsize=max_clients,
            ttl=window_seconds,
        )
        self._lock = asyncio.Lock()

    async def check(self, client_id: str) -> RateLimitDecision:
        now = time.monotonic()
        cutoff = now - self._window

        async with self._lock:
            timestamps = self._requests.get(client_id, deque())
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= self._limit:
                retry_after = max(1, math.ceil(self._window - (now - timestamps[0])))
                self._requests[client_id] = timestamps
                return RateLimitDecision(False, retry_after)

            timestamps.append(now)
            self._requests[client_id] = timestamps
            return RateLimitDecision(True)
