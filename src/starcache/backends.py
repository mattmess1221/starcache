import abc
import logging
import sys

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


logger = logging.getLogger(__name__)


class CacheBackend(abc.ABC):
    """Abstract base class for cache backends.

    Implement this to create custom cache backends, such as for Redis, Valkey,
    Memcached, or Amazon RDS.

    Due to the simplicity of the cache interface, only two methods need to be
    implemented: `_get` and `_set`. Thus, only the default MemoryBackend is provided
    out of the box.

    Examples:
        A redis backend implementation:

        ```py
        import redis.asyncio as aioredis


        class RedisBackend(CacheBackend):
            def __init__(self, redis_url: str):
                self.redis = aioredis.from_url(redis_url)

            async def get(self, key: str) -> bytes | None:
                return await self.redis.get(key)

            async def set(self, key: str, value: bytes) -> None:
                await self.redis.set(key, value)
        ```

        A memcached backend implementation:

        ```py
        import aiomcache


        class MemcachedBackend(CacheBackend):
            def __init__(self, host: str, port: int):
                self.client = aiomcache.Client(host, port)

            async def get(self, key: str) -> bytes | None:
                return await self.client.get(key.encode())

            async def set(self, key: str, value: bytes) -> None:
                await self.client.set(key.encode(), value)
        ```

    """

    @abc.abstractmethod
    async def get(self, key: str, /) -> bytes | None:
        """Get a cached item by key.

        Args:
            key (str): The cache key.

        Returns:
            bytes | None: The cached item data or None if not found.

        """

    @abc.abstractmethod
    async def set(self, key: str, value: bytes, /) -> None:
        """Set a cached item by key.

        Args:
            key (str): The cache key.
            value (bytes): The cached item data.

        """


class MemoryBackend(CacheBackend):
    """The default In-memory cache backend.

    Not suitable for production use or when using multiple workers.
    """

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    @override
    async def get(self, key: str) -> bytes | None:
        return self.store.get(key)

    @override
    async def set(self, key: str, value: bytes) -> None:
        self.store[key] = value
