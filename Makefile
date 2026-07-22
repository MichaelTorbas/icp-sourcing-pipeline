.PHONY: install test run lint

install:
	uv sync

test:
	uv run pytest

# pipeline.main doesn't exist yet — this is a forward reference for once
# the adapters and pipeline entrypoint are built.
run:
	uv run python -m pipeline.main --config config.yaml

lint:
	uv run ruff check .
	uv run ruff format --check .
