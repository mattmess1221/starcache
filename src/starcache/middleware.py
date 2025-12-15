import logging
import sys
from collections.abc import Mapping

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from .backends import CacheBackend, MemoryBackend
from .cached_responses import CachedResponse, CacheItem, CacheRequest
from .serializers import JSONSerializer, Serializer
from .utils import make_key, parse_cache_control
from .vary import VaryHeaderNormalizer

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


logger = logging.getLogger(__name__)


class StarcacheMiddleware(BaseHTTPMiddleware):
    """Middleware for caching HTTP responses based on request characteristics.

    Response caching is determined by the presence and values of `Cache-Control` headers
    in both the request and response.

    Note:
        This middleware should be placed at the start of the middleware stack to ensure
        proper handling of caching and `Vary` headers.

        When using the `add_middleware` utility, this means registering it last.

    Args:
        backend (CacheBackend | None): The cache backend to use. Defaults to
            `MemoryBackend` if not provided.
        serializer (Serializer | None): The serializer to use for caching responses.
            Defaults to `JSONSerializer` if not provided.
        vary_normalizers (Mapping[str, VaryHeaderNormalizer] | None): A mapping of
            header names to their corresponding normalizer functions for handling
            `Vary` headers.

    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        backend: CacheBackend | None = None,
        serializer: Serializer | None = None,
        vary_normalizers: Mapping[str, VaryHeaderNormalizer] | None = None,
    ) -> None:
        super().__init__(app)
        if backend is None:  # pragma: no cover
            backend = MemoryBackend()
        if serializer is None:  # pragma: no cover
            serializer = JSONSerializer()
        self.backend = backend
        self.serializer = serializer
        self.vary_normalizers = {
            k.lower(): v for k, v in (vary_normalizers or {}).items()
        }

    @override
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method not in ("GET", "HEAD"):
            return await call_next(request)

        request = CacheRequest(request.scope, request.receive)

        if self.should_lookup_cache(request):
            response = await self.get_cached_response(request)
            if response is not None and response.validate(request):
                logger.debug("Cache hit for request: %s", request.url)
                response.prepare_headers(hit=True)
                return response
            logger.debug("Cache miss for request: %s", request.url)

        downstream_response = await call_next(request)
        if not self.should_store_response(request, downstream_response):
            logger.debug("Response not storable for request: %s", request.url)
            return downstream_response

        logger.debug("Caching request %s", request.url)
        response = await self.set_cached_response(request, downstream_response)

        response.prepare_headers(hit=False)
        return response

    def should_lookup_cache(self, request: CacheRequest) -> bool:
        return (
            "no-cache" not in request.cache_control
            and request.cache_control.get("max-age") != 0
        )

    def should_store_response(self, request: CacheRequest, response: Response) -> bool:
        if "no-store" in request.cache_control:
            return False

        res_cache_control = parse_cache_control(response)
        if "private" in res_cache_control:
            return False
        # authorized requests only be cached if explicitly marked public
        if "public" not in res_cache_control and "authorization" in request.headers:
            return False

        # max-age=0 is common with "no-store, max-age=0" on responses
        maxage = res_cache_control.get("s-maxage", res_cache_control.get("max-age", 0))
        return maxage != 0

    async def get_cached_response(self, request: Request) -> CachedResponse | None:
        key = await self.make_request_cache_key(request)
        data = await self.backend.get(key)
        if data is None:
            return None

        try:
            cache_item: CacheItem = self.serializer.deserialize(data)
            return CachedResponse.from_cache(key, cache_item)
        except Exception:  # pragma: no cover
            logger.exception("Failed to deserialize cached response with key: %r", key)
            return None

    async def set_cached_response(
        self, request: Request, response: Response
    ) -> CachedResponse:
        key = await self.make_request_cache_key(request, response)
        cached_response = await CachedResponse.wrap(key, response)
        try:
            data = self.serializer.serialize(cached_response.to_cache())
        except Exception:  # pragma: no cover
            logger.exception("Failed to serialize cached response for: %s", request.url)
            return cached_response

        try:
            await self.backend.set(key, data)
        except Exception:  # pragma: no cover
            logger.exception(
                "Failed to set cached response for %s with key %s", request.url, key
            )
        return cached_response

    async def load_vary_response_headers(self, key: str) -> list[str]:
        try:
            vary_headers_data = await self.backend.get(key)
        except Exception:  # pragma: no cover
            logger.exception("Failed to get cached vary headers with key: %r", key)
            return []
        if vary_headers_data is None:
            return []

        try:
            vary_headers = self.serializer.deserialize(vary_headers_data)
        except Exception:  # pragma: no cover
            logger.exception(
                "Failed to deserialize cached vary headers with key: %r", key
            )
            return []
        return list(vary_headers)

    async def save_vary_response_headers(
        self, key: str, response: Response
    ) -> list[str]:
        vary_headers = sorted(
            {x.strip().lower() for x in response.headers.get("vary", "").split(",")}
        )

        try:
            vary_headers_data = self.serializer.serialize(vary_headers)
        except Exception:  # pragma: no cover
            logger.exception("Failed to serialize vary headers for key: %r", key)
            return []

        try:
            await self.backend.set(key, vary_headers_data)
        except Exception:  # pragma: no cover
            logger.exception("Failed to cache vary headers with key: %r", key)

        return vary_headers

    async def resolve_vary_response_headers(
        self, request: Request, response: Response | None = None
    ) -> list[str]:
        vary_key = make_key("vary", request.url)
        if response is None:
            return await self.load_vary_response_headers(vary_key)

        return await self.save_vary_response_headers(vary_key, response)

    async def make_request_cache_key(
        self, request: Request, response: Response | None = None
    ) -> str:
        vary_headers = await self.resolve_vary_response_headers(request, response)

        vary_parts = [
            f"{header}={self.normalize_vary_header(request, header)}"
            for header in sorted({s.lower() for s in vary_headers})
        ]

        return make_key("cache", request.url, *vary_parts)

    def normalize_vary_header(self, request: Request, header: str) -> str | None:
        """Implement in subclass to normalize a Vary header value."""
        value = request.headers.get(header)
        if value is not None and header in self.vary_normalizers:
            return self.vary_normalizers[header](value)
        return value
