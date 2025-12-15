import contextlib
import re
from collections.abc import Iterable, Sequence
from operator import itemgetter
from typing import Protocol


class VaryHeaderNormalizer(Protocol):
    def __call__(self, value: str, /) -> str: ...


_weighted_values_re = re.compile(r"^(\w+|\*)(?:;q=([\d.]+))?")
_simple_values_re = re.compile(r"[a-z]{2,8}")


def _parse_weighted_values(values: str) -> list[tuple[str, float]]:
    """Parse a weighted header value into a list of (value, weight) tuples.

    Returned value will be sorted by weight in descending order, so the first item
    is the most preferred.
    """
    weights: list[tuple[str, float]] = []
    for part in values.split(","):
        match = _weighted_values_re.match(part.strip().lower())
        if match:
            value = match.group(1)
            q_value = match.group(2)
            wgt = 1.0
            if q_value is not None:
                with contextlib.suppress(ValueError):
                    wgt = float(q_value)
            weights.append((value, wgt))

    return sorted(weights, key=itemgetter(1), reverse=True)


def _resolve_preference(supported: Iterable[str]) -> tuple[str, set[str]]:
    """Resolve preferred and supported values from an iterable.

    The preferred value is the first item in the iterable and should be used for "*"
    values.

    Returns:
        tuple[str, set[str]]: A tuple containing the preferred value and a set of
            supported values.

    """
    supported = list(supported)
    preferred = supported[0]
    supported = set(supported)
    return preferred, supported


def weighted_normalizer(
    supported: Iterable[str],
    *,
    default: str = "None",
) -> VaryHeaderNormalizer:
    """Define a vary normalizer to filter supported weighted values.

    Generally used for accept-encoding or accept-language headers.
    """
    preferred, supported = _resolve_preference(supported)

    def normalize(value: str) -> str:
        weights = _parse_weighted_values(value)
        for val, _ in weights:
            if val == "*":
                return preferred
            if val in supported:
                return val
        return default

    return normalize


def simple_normalizer(
    supported: Sequence[str], *, default: str = "None"
) -> VaryHeaderNormalizer:
    """Define a vary normalizer to filter supported values, ignoring weights.

    Behaves similar to starlatte-compress==1.6.1's handling of Accept-Encoding, where it
    checks, in order, if zstd, br, or gzip is requested.

    Checking for `*` is not supported.
    """

    def normalizer(value: str) -> str:
        values = frozenset(_simple_values_re.findall(value.lower()))
        for item in supported:
            if item in values:
                return item
        return default

    return normalizer
