test:
    uv run --group tests pytest

cover:
    tox

check:
    uv run --group=lint ruff check
    uv run --group=lint ruff format --check

lint:
    uv run --group=lint ruff check --fix
    uv run --group=lint ruff format
