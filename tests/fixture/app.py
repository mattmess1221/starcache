import random
import string

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from starcache import StarcacheMiddleware, vary


def hello_world(_: Request) -> Response:
    return PlainTextResponse(
        "Hello, World!",
        headers={
            "Cache-Control": "public, max-age=60",
        },
    )


def random_view(_: Request) -> Response:
    random_string = "".join(random.choices(string.printable, k=10))  # noqa: S311
    return PlainTextResponse(
        random_string,
        headers={
            "Cache-Control": "public, max-age=60",
        },
    )


def authorized(request: Request) -> Response:
    # route will not be cached due to presence of Authorization header and lack of
    # 'public' directive
    assert "authorization" in request.headers
    return PlainTextResponse(
        "Authorized access",
        headers={
            "Cache-Control": "max-age=60",
        },
    )


def private(_: Request) -> Response:
    # route will not be cached due to 'private' directive
    return PlainTextResponse(
        "Private content",
        headers={
            "Cache-Control": "private, max-age=60",
        },
    )


def uncached(_: Request) -> Response:
    return PlainTextResponse("This route is not cached.")


def varied_view(request: Request) -> Response:
    user_agent = request.headers.get("user-agent", "unknown")
    return PlainTextResponse(
        user_agent,
        headers={
            "Cache-Control": "public, max-age=60",
            "Vary": "User-Agent",
        },
    )


def server_maxage(_: Request) -> Response:
    return PlainTextResponse(
        "Server max-age response",
        headers={
            "Cache-Control": "public, s-maxage=120, max-age=60",
        },
    )


def large_data(_: Request) -> Response:
    data = "A" * 10_000  # 10 KB of data
    return PlainTextResponse(
        data,
        headers={
            "Cache-Control": "public, max-age=60",
        },
    )


# uvicorn --factory tests.fixture.app:create_app --reload
def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/", hello_world, methods=["GET", "POST"]),
            Route("/random", random_view),
            Route("/authorized", authorized),
            Route("/private", private),
            Route("/uncached", uncached),
            Route("/varied", varied_view),
            Route("/server-maxage", server_maxage),
            Route("/large-data", large_data),
        ],
        middleware=[
            Middleware(
                StarcacheMiddleware,
                vary_normalizers={
                    "accept-encoding": vary.simple_normalizer(["gzip"]),
                },
            ),
            # gzip middleware should be after StarcacheMiddleware to ensure caching
            # works correctly with compressed responses
            Middleware(GZipMiddleware),
        ],
    )
