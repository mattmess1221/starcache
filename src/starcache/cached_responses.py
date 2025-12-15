import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from starlette.requests import Request
from starlette.responses import Response

from .utils import CacheControl, parse_cache_control

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from starlette.types import Message, Receive, Scope, Send


class CacheItem(TypedDict):
    """A cached item stored in the cache backend."""

    cache_id: str
    """The unique cache key ID, as a UUID string."""
    date: str
    """The datetime the response was cached, stored in ISO 8601 format."""
    messages: list[Message]
    """The ASGI messages comprising the cached response.

    Standard responses will have at least two messages:
    - `{"type": "http.response.start",
        "status": int,
        "headers": list[tuple[bytes, bytes]]}`
    - `{"type": "http.response.body",
        "body": bytes,
        "more_body": bool}`
    """


class CacheRequest(Request):
    @property
    def cache_control(self) -> CacheControl:
        if not hasattr(self, "_cache_control"):
            self._cache_control = parse_cache_control(self)
        return self._cache_control


class CachedResponse(Response):
    """A cached response whose messages can be replayed."""

    cache_id: uuid.UUID
    """A unique ID for the cache, for debugging purposes."""
    cache_key: str
    """The key used to store the response, for debugging purposes."""
    date: datetime
    """The datetime the response was cached."""
    messages: list[Message]
    """The ASGI messages comprising the cached response."""

    def __init__(
        self,
        cache_id: uuid.UUID,
        cache_key: str,
        date: datetime,
        messages: list[Message],
    ) -> None:
        if (
            not messages or messages[0]["type"] != "http.response.start"
        ):  # pragma: no cover
            raise ValueError("Response messages must start with http.response.start")

        self.cache_id = cache_id
        self.cache_key = cache_key
        self.date = date
        self.messages = messages

        self.status_code = messages[0]["status"]
        self.raw_headers = messages[0]["headers"]

    def prepare_headers(self, *, hit: bool) -> None:
        """Prepare headers for sending the cached response."""
        self.headers.update(
            {
                # Note: Date is added automatically by the http server.
                # Adding it here would be incorrect.
                "age": str(int(self.age.total_seconds())),
                "expires": self.expires.strftime("%a, %d %b %Y %H:%M:%S GMT"),
                "x-cache": "hit" if hit else "miss",
                "x-cache-id": str(self.cache_id),
                "x-cache-key": self.cache_key,
            }
        )

    def to_cache(self) -> CacheItem:
        """Convert the CachedResponse to a serializable CacheItem."""
        return CacheItem(
            cache_id=str(self.cache_id),
            date=self.date.isoformat(),
            messages=self.messages,
        )

    @classmethod
    def from_cache(cls, key: str, cache_item: CacheItem) -> Self:
        """Create a CachedResponse instance from a deserialized cache item."""
        return cls(
            cache_id=uuid.UUID(cache_item["cache_id"]),
            cache_key=key,
            date=datetime.fromisoformat(cache_item["date"]),
            messages=cache_item["messages"],
        )

    @classmethod
    async def wrap(cls, key: str, response: Response) -> Self:
        """Wrap the response to capture ASGI messages so it is ready for reuse.

        This consumes the response.
        """
        messages = []

        async def _receive() -> Message:  # pragma: no cover
            return await asyncio.Queue[Message]().get()

        async def _send(message: Message) -> None:
            messages.append(message)

        await response({}, _receive, _send)
        return cls(
            cache_id=uuid.uuid4(),
            cache_key=key,
            date=datetime.now(timezone.utc),
            messages=messages,
        )

    @property
    def cache_control(self) -> CacheControl:
        if not hasattr(self, "_cache_control"):
            self._cache_control = parse_cache_control(self)
        return self._cache_control

    @property
    def maxage(self) -> int:
        """The max-age or s-maxage as defined in the cache-control header."""
        if "s-maxage" in self.cache_control:
            return self.cache_control["s-maxage"]
        if "max-age" in self.cache_control:
            return self.cache_control["max-age"]

        raise AssertionError(  # pragma: no cover
            "Response with missing max-age or s-maxage should not have been cached"
        )

    @property
    def expires(self) -> datetime:
        """The expiration time of the cached response."""
        return self.date + timedelta(seconds=self.maxage)

    @property
    def age(self) -> timedelta:
        """The age of the cached response."""
        return datetime.now(timezone.utc) - self.date

    @property
    def stale(self) -> timedelta:
        """The time since the cached response expired."""
        return datetime.now(timezone.utc) - self.expires

    def validate(self, request: CacheRequest) -> bool:
        # NOTE: browsers don't support min-fresh, stale-if-error, so we skip it for now

        age = int(self.age.total_seconds())
        if "max-age" in request.cache_control:
            return age <= request.cache_control["max-age"]

        if age > self.maxage:
            max_stale = request.cache_control.get("max-stale", 0)
            return max_stale > self.stale.total_seconds()

        return True

    @override
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Send the cached response messages to the ASGI send callable."""
        for message in self.messages:
            await send(message)
