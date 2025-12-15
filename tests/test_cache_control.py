import pytest
from starlette.requests import Request

from starcache.utils import CacheControl, parse_cache_control


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (
            "public, max-age=3600, no-transform",
            {"public": True, "max-age": 3600, "no-transform": True},
        ),
        (
            "private, no-cache, max-stale=120",
            {"private": True, "no-cache": True, "max-stale": 120},
        ),
        ("no-store", {"no-store": True}),
        ("max-age=0", {"max-age": 0}),
        ("", {}),
        # invalid maxage value
        ("max-age=invalid", {"max-age": 0}),
        # negative maxage
        ("max-age=-400", {"max-age": 0}),
        # non-numeric maxage
        ("max-age=145.0", {"max-age": 0}),
        # bare max-age
        ("max-age", {"max-age": 0}),
    ],
)
def test_parse_cache_control(header: str, expected: CacheControl) -> None:
    request = Request(
        scope={
            "type": "http",
            "headers": [
                (b"cache-control", header.encode("utf-8")),
            ],
        }
    )
    directives = parse_cache_control(request)
    assert directives == expected
