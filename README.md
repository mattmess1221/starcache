# Starcache

[![PyPI version](https://badge.fury.io/py/starcache.svg)](https://badge.fury.io/py/starcache)
[![Tests](https://github.com/mattmess1221/starcache/actions/workflows/ci.yaml/badge.svg)](https://github.com/mattmess1221/starcache/actions/workflows/ci.yaml)
[![Code Coverage](https://codecov.io/gh/mattmess1221/starcache/branch/main/graph/badge.svg)](https://codecov.io/gh/mattmess1221/starcache)

A modern, high-performance HTTP caching library for Starlette and FastAPI.

This library was created for self-hosted applications in an air-gapped environment where
using third-party caching solutions is not an option. It provides a flexible middleware
that can be easily integrated into existing FastAPI or Starlette applications to enable
HTTP caching based on standard HTTP caching headers.

## Features

- Simple and intuitive API
- Supports custom serializers and cache backends (see examples)
- In-memory caching backend included for development and testing purposes
- Full control over caching behavior via request and response headers
- Public and private caching support
- Supports `Vary` response headers for caching based on request headers with customizable normalization

## Installation

```bash
pip install starcache
```

## Usage

1. Add the `StarcacheMiddleware` at the start of your middleware stack. If using the `add_middleware` utility, this means registering it last.
   - Especially make sure to add it before any middleware that adds a `Vary` header to the response, such as `GZipMiddleware`.
2. If needed, specify a custom backend and serializer when adding the middleware.
3. Configure caching for specific responses by adding appropriate `Cache-Control` headers.
4. If your responses change based on the value of a request header, such as `Accept`, make sure to include the header's name in the `Vary` response header.

### Basic

Basic usecases which only need non-persistent in-memory caching should only be used during development or testing. Below is a simple example of how to use Starcache with FastAPI:

```python
import random
import string

from fastapi import FastAPI, Response
from fastapi.middleware.gzip import GZipMiddleware
from starcache import StarcacheMiddleware

app = FastAPI()
app.add_middleware(GZipMiddleware)
# add gzip middleware first, as well as any other middlewares which add a Vary header.
app.add_middleware(StarcacheMiddleware)


@app.get("/data")
async def get_data(response: Response):
    # Opt in to caching for this response by adding the cache-control header
    response.headers["Cache-Control"] = "public, max-age=3600"
    return {
        "random_message": ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
    }

```

### Valkey/Redis backend

A common use case is to use Valkey or Redis as the cache backend. Below is an example of how to implement a Redis backend for Starcache using the [redis](https://pypi.org/project/redis/) module.

```python
import redis.asyncio as redis
from fastapi import FastAPI

from starcache import StarcacheMiddleware, CacheBackend


class RedisBackend(CacheBackend):
    def __init__(self):
        # Connect to a localhost redis or valkey server
        self.client = aioredis.Redis(host='localhost', port=6379, db=0)
        self.ttl = 31536000  # 1 year in seconds

    async def get(self, key: str) -> bytes | None:
        return await self.client.get(key)

    async def set(self, key: str, value: bytes) -> None:
        # ttl only effects how long the cache entry is stored
        # The actual ttl is done via the cache-control header max-age directive
        await self.client.set(key, value, ex=self.ttl)


app = FastAPI()
app.add_middleware(StarcacheMiddleware, backend=RedisBackend())
```

### Vary normalization/deduplication

If your responses vary based on certain request headers, you can configure custom normalization functions for those headers using the `vary_normalizers` parameter of the `StarcacheMiddleware`. This is useful for headers like `Accept-Encoding` and `Accept-Language`, where you may want to normalize the values to a specific set.

The `starcache.vary` module provides some built-in normalizers that you can use:

```py
from starlette_compress import CompressMiddleware
from starcache import vary

app.add_middleware(CompressMiddleware)
app.add_middleware(
    StarcacheMiddleware,
    vary_normalizers={
        # Normalize Accept-Encoding to prefer zstd, br, then gzip, ignoring weights.
        # This copies the behavior of starlette-compress
        "accept-encoding": vary.simple_normalizer(["zstd", "br", "gzip"]),
        # Normalize Accept-Language to consider only en, fr, and de with weights
        "accept-language": vary.weighted_normalizer(["en", "fr", "de"]),
    },
)
```

Custom normalizers can also be defined as callables that take a header string value and return a normalized string.

```py
def my_custom_normalizer(value: str) -> str:
    # Custom normalization logic here
    return normalized_value


app.add_middleware(
    StarcacheMiddleware,
    vary_normalizers={
       "my-header": my_custom_normalizer,
    },
)
```
