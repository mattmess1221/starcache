from collections.abc import Generator
from typing import Any

import fakeredis
import pytest
from starlette.testclient import TestClient

redis_server = fakeredis.FakeServer()


@pytest.fixture
def redis_client() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(server=redis_server)


@pytest.fixture
def client(redis_client: fakeredis.FakeRedis) -> Generator[TestClient, Any, None]:
    from fixture.redis_app import create_app

    app = create_app(fakeredis.aioredis.FakeRedis(server=redis_server))

    try:
        with TestClient(app) as client:
            yield client
    finally:
        assert redis_client is not None
        redis_client.flushdb()


def test_redis_cache_set_get(
    client: TestClient, redis_client: fakeredis.FakeRedis
) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["x-cache"] == "miss"

    assert redis_client is not None
    keys = redis_client.keys()
    assert isinstance(keys, list)
    assert len(keys) == 2  # One for response body, one for vary headers
