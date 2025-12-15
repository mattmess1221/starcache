from collections.abc import Generator

import pytest
from freezegun import freeze_time
from starlette.testclient import TestClient

from fixture.app import create_app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app = create_app()

    with TestClient(app) as client:
        yield client


# repeat to test cache is not presisted between tests
@pytest.mark.repeat(2)
@freeze_time("2024-01-01")
def test_e2e(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers.get("x-cache") == "miss"
    assert response.headers.get("Cache-Control") == "public, max-age=60"
    assert response.headers.get("Expires") == "Mon, 01 Jan 2024 00:01:00 GMT"


def test_cache_hit(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers.get("x-cache") == "miss"

    response = client.get("/")
    assert response.status_code == 200
    assert response.headers.get("x-cache") == "hit"
    assert response.headers.get("Age") == "0"


def test_random_view_caching(client: TestClient) -> None:
    response1 = client.get("/random")
    assert response1.status_code == 200
    assert response1.headers.get("x-cache") == "miss"
    message1 = response1.text

    response2 = client.get("/random")
    assert response2.status_code == 200
    assert response2.headers.get("x-cache") == "hit"
    message2 = response2.text

    assert message1 == message2


def test_cache_expiry(client: TestClient) -> None:
    with freeze_time("2024-01-01 00:00:00Z") as time:
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers.get("x-cache") == "miss"

        time.tick(delta=120)

        response = client.get("/")
        assert response.status_code == 200
        age = response.headers.get("age")
        assert response.headers.get("x-cache") == "miss", (
            f"Cache was not expired, is {age}s old"
        )


def test_uncached_response(client: TestClient) -> None:
    response = client.get("/uncached")
    assert response.status_code == 200
    assert "x-cache" not in response.headers


def test_uncached_request_method(client: TestClient) -> None:
    response = client.post("/")
    assert response.status_code == 200
    assert "x-cache" not in response.headers


def test_uncached_request_headers(client: TestClient) -> None:
    response = client.get(
        "/uncached",
        headers={
            "Cache-Control": "no-cache, max-age=0",
        },
    )
    assert response.status_code == 200
    assert "x-cache" not in response.headers


def test_varied_response_caching(client: TestClient) -> None:
    user_agent_1 = "test-agent-1"
    user_agent_2 = "test-agent-2"

    response1 = client.get(
        "/varied",
        headers={"User-Agent": user_agent_1},
    )
    assert response1.status_code == 200
    assert response1.headers.get("x-cache") == "miss"
    assert response1.text == user_agent_1

    response2 = client.get(
        "/varied",
        headers={"User-Agent": user_agent_2},
    )
    assert response2.status_code == 200
    assert response2.headers.get("x-cache") == "miss"
    assert response2.text == user_agent_2

    # Repeat request with first User-Agent, should be a cache hit
    response3 = client.get(
        "/varied",
        headers={"User-Agent": user_agent_1},
    )
    assert response3.status_code == 200
    assert response3.headers.get("x-cache") == "hit"
    assert response3.text == user_agent_1


def test_authorized_response_is_not_cached(client: TestClient) -> None:
    response = client.get(
        "/authorized",
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 200
    assert "x-cache" not in response.headers


def test_private_response_is_not_cached(client: TestClient) -> None:
    response = client.get("/private")
    assert response.status_code == 200
    assert "x-cache" not in response.headers


def test_no_store_request_is_not_cached(client: TestClient) -> None:
    response = client.get(
        "/",
        headers={"Cache-Control": "no-store"},
    )
    assert response.status_code == 200
    assert "x-cache" not in response.headers


def test_server_max_age(client: TestClient) -> None:
    with freeze_time("2024-01-01 00:00:00Z") as time:
        for hit in ("miss", "hit", "miss"):
            response = client.get("/server-maxage")
            assert response.status_code == 200
            assert response.headers.get("x-cache") == hit

            time.tick(delta=61)


def test_client_max_age(client: TestClient) -> None:
    with freeze_time("2024-01-01 00:00:00Z") as time:
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers.get("x-cache") == "miss"

        time.tick(delta=31)

        response = client.get(
            "/",
            headers={"Cache-Control": "max-age=30"},
        )
        assert response.status_code == 200
        assert response.headers.get("x-cache") == "miss"


def test_compressed_response_caching(client: TestClient) -> None:
    for enc in ("identity", "gzip"):
        for hit in ("miss", "hit"):
            response = client.get(
                "/large-data",
                headers={"Accept-Encoding": enc},
            )
            assert response.status_code == 200
            assert response.headers["vary"] == "Accept-Encoding"
            assert response.headers["x-cache"] == hit
            if enc == "gzip":
                assert response.headers.get("Content-Encoding") == "gzip"
            else:
                assert response.headers.get("Content-Encoding") is None


@pytest.mark.parametrize(
    "encodings",
    [
        ["gzip", "gzip, br"],
        ["br, zstd", "identity"],
    ],
)
def test_compression_vary_dedupe(encodings: list[str], client: TestClient) -> None:
    # Only gzip is supported on the test client, so all requests
    # wanting gzip should hit the same cached response.
    # Unsupported encodings should fall back to identity.
    cache_id = None
    for encoding in encodings:
        response = client.get(
            "/large-data",
            headers={"Accept-Encoding": encoding},
        )
        assert response.status_code == 200
        if cache_id is None:
            cache_id = response.headers.get("x-cache-id")
            assert cache_id is not None
        else:
            assert response.headers.get("x-cache-id") == cache_id


def test_response_cache_id_is_recreated_after_expire(client: TestClient) -> None:
    with freeze_time("2024-01-01 00:00:00Z") as time:
        response1 = client.get("/")
        assert response1.status_code == 200
        assert response1.headers.get("x-cache") == "miss"
        cache_id_1 = response1.headers.get("x-cache-id")
        assert cache_id_1 is not None

        response2 = client.get("/")
        assert response2.status_code == 200
        assert response2.headers.get("x-cache") == "hit"
        assert response2.headers.get("x-cache-id") == cache_id_1

        time.tick(delta=61)

        response3 = client.get("/")
        assert response3.status_code == 200
        assert response3.headers.get("x-cache") == "miss"
        cache_id_3 = response3.headers.get("x-cache-id")
        assert cache_id_3 is not None
        assert cache_id_3 != cache_id_1
