import hashlib
import logging
import re
from typing import Literal, Protocol, TypedDict, cast

from starlette.datastructures import Headers

uvicorn_logger = logging.getLogger("uvicorn.error")

ANSI_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

CacheControl = TypedDict(
    "CacheControl",
    {
        "max-age": int,
        "max-stale": int,
        "min-fresh": int,
        "s-maxage": int,
        "no-cache": Literal[True],
        "no-store": Literal[True],
        "no-transform": Literal[True],
        "only-if-cached": Literal[True],
        "must-revalidate": Literal[True],
        "proxy-revalidate": Literal[True],
        "must-understand": Literal[True],
        "private": Literal[True],
        "public": Literal[True],
        "immutable": Literal[True],
        "stale-while-revalidate": int,
        "stale-if-error": int,
    },
    total=False,
)


class ServerCacheControl(TypedDict, total=False):
    max_age: int
    s_maxage: int
    no_cache: Literal[True]
    no_store: Literal[True]
    no_transform: Literal[True]
    must_revalidate: Literal[True]
    proxy_revalidate: Literal[True]
    must_understand: Literal[True]
    private: Literal[True]
    public: Literal[True]
    immutable: Literal[True]
    stale_while_revalidate: int
    stale_if_error: int


class SupportsHeaders(Protocol):
    @property
    def headers(self) -> Headers: ...


def parse_cache_control(req_or_res: SupportsHeaders) -> CacheControl:
    directives = {}
    for part in req_or_res.headers.get("cache-control", "").split(","):
        key = part.strip()
        value = None
        if "=" in key:
            key, value = part.split("=", 1)
            value = value.strip()

        key = key.strip().lower()
        if not key or key not in CacheControl.__annotations__:
            continue

        if CacheControl.__annotations__.get(key) is int:
            try:
                directives[key] = max(0, int(value or "0"))
            except ValueError:
                directives[key] = 0
        else:
            directives[key] = True

    return cast("CacheControl", directives)


def make_key(*parts: object) -> str:
    return hashlib.sha1(
        "::".join(str(s) for s in parts).encode(),
        usedforsecurity=False,
    ).hexdigest()
