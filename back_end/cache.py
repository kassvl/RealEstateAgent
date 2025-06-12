"""Redis-backed simple cache for HTTP and geocoding responses."""
import json
import hashlib
import os
import logging
from typing import Optional

import redis
from redis.exceptions import RedisError

_logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
_redis_client: Optional[redis.Redis] = None


# ------------------ In-memory fallback ------------------

class _DummyCache:
    """Simple dict-backed replacement when Redis is unavailable."""

    def __init__(self):
        self._store: dict[str, tuple[str, float]] = {}

    def get(self, key: str):
        v = self._store.get(key)
        if not v:
            return None
        val, exp = v
        import time

        if exp and exp < time.time():
            del self._store[key]
            return None
        return val

    def setex(self, key: str, ttl: int, value: str):
        import time

        self._store[key] = (value, time.time() + ttl)


_dummy_cache = _DummyCache()


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        try:
            client = redis.Redis.from_url(_REDIS_URL, decode_responses=True)
            # test connection once
            client.ping()
            _redis_client = client
        except RedisError:
            _logger.warning("Redis not reachable → using in-memory cache")
            _redis_client = _dummy_cache  # type: ignore
    return _redis_client


def _make_key(namespace: str, raw: str) -> str:
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"


def get_cached(namespace: str, raw: str) -> Optional[str]:
    key = _make_key(namespace, raw)
    return get_redis().get(key)


def set_cached(namespace: str, raw: str, value: str, ttl: int = 86400):
    key = _make_key(namespace, raw)
    get_redis().setex(key, ttl, value)


# Convenience wrappers -------------------------------------

def http_get_cached(url: str) -> Optional[str]:
    return get_cached("http", url)


def http_set_cached(url: str, text: str, ttl: int = 86400):
    set_cached("http", url, text, ttl)


def geo_get_cached(addr: str) -> Optional[str]:
    return get_cached("geo", addr)


def geo_set_cached(addr: str, latlon_json: str, ttl: int = 604800):
    set_cached("geo", addr, latlon_json, ttl)
