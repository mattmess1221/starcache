import abc
import base64
import json
import sys
from typing import Any

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class Serializer(abc.ABC):
    """Abstract base class for serializers.

    In addition to the standard json types, serializers must also support `bytes`.
    """

    @abc.abstractmethod
    def serialize(self, item: Any) -> bytes: ...
    @abc.abstractmethod
    def deserialize(self, data: bytes) -> Any: ...


class Encoder(json.JSONEncoder):
    @override
    def default(self, o: object) -> object:
        if isinstance(o, bytes):
            return {
                "__type__": "bytes",
                "data": base64.b64encode(o).decode("ascii"),
            }

        raise super().default(o)  # pragma: no cover


class Decoder(json.JSONDecoder):
    def __init__(self) -> None:
        super().__init__(object_hook=self._object_hook)

    def _object_hook(self, obj: object) -> object:
        match obj:
            case {"__type__": "bytes", "data": str(data)}:
                return base64.b64decode(data.encode("ascii"))
            case _:
                return obj


class JSONSerializer(Serializer):
    """The default JSON serializer."""

    def serialize(self, item: Any) -> bytes:
        return json.dumps(item, cls=Encoder).encode()

    def deserialize(self, data: bytes) -> Any:
        return json.loads(data.decode(), cls=Decoder)
