"""In-memory TTL cache service."""
from cachetools import TTLCache


class CacheService:
    def __init__(self, maxsize: int = 256, ttl: int = 60):
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)

    def get(self, key: str):
        return self._cache.get(key)

    def set(self, key: str, value):
        self._cache[key] = value

    def invalidate(self, key: str):
        self._cache.pop(key, None)

    def clear(self):
        self._cache.clear()


cache = CacheService()
