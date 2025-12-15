import pytest

from starcache import vary


@pytest.mark.parametrize(
    ("weights", "result"),
    [
        ("value2, value3", "value2"),
        ("value1, value2;q=0.8", "value1"),
        ("unknown, another", "None"),
        ("*;q=0.5, value3;q=0.8", "value3"),
        ("value4, *;q=0.1", "value1"),
        # invalid weights don't crash the normalizer
        ("value1;q=0.9, value2;Q=0.5", "value1"),
        ("invalid", "None"),
        ("value1;Q=abc", "value1"),
        ("value1;Q", "value1"),
        ("value1;p=0.8", "value1"),
        ("value1;", "value1"),
        ("", "None"),
    ],
)
def test_weighted_normalizer(weights: str, result: str) -> None:
    normalizer = vary.weighted_normalizer(
        ["value1", "value2", "value3"],
    )
    assert normalizer(weights) == result


@pytest.mark.parametrize(
    ("values", "result"),
    [
        ("bbb, ccc", "bbb"),
        ("aaa, bbb;q=0.8", "aaa"),
        ("aab, cdd", "None"),
        ("*;q=0.5, ccc;q=0.8", "ccc"),
        ("ddd, *;q=0.1", "None"),
    ],
)
def test_simple_normalizer(values: str, result: str) -> None:
    normalizer = vary.simple_normalizer(
        ["aaa", "bbb", "ccc"],
    )
    assert normalizer(values) == result
