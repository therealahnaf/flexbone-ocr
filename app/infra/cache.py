import asyncio

from cachetools import TTLCache

from app.domain.models import CachedOcrResult


class InMemoryOcrCache:
    def __init__(self, max_entries: int, ttl_seconds: int):
        self._cache: TTLCache[str, CachedOcrResult] = TTLCache(
            maxsize=max_entries,
            ttl=ttl_seconds,
        )
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> CachedOcrResult | None:
        async with self._lock:
            return self._cache.get(key)

    async def set(self, key: str, value: CachedOcrResult) -> None:
        async with self._lock:
            self._cache[key] = value
