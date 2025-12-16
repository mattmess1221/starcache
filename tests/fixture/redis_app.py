import redis.asyncio as redis
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from starcache import CacheBackend, StarcacheMiddleware


def index(_: Request) -> Response:
    return PlainTextResponse(
        "Hello, Starcache!", headers={"Cache-Control": "max-age=60"}
    )


class RedisBackend(CacheBackend):
    def __init__(self, redis: redis.Redis) -> None:
        self.redis = redis

    async def get(self, key: str) -> bytes | None:
        return await self.redis.get(key)

    async def set(self, key: str, value: bytes) -> None:
        await self.redis.set(key, value)


def create_app(redis: redis.Redis) -> Starlette:
    return Starlette(
        routes=[
            Route("/", index),
        ],
        middleware=[
            Middleware(
                StarcacheMiddleware,
                backend=RedisBackend(redis),
            ),
        ],
    )
