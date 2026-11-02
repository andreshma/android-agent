.PHONY: install lint format type test check all

install:
	pip install -e ".[dev,anthropic]"
	pre-commit install

lint:
	ruff check .

format:
	ruff format .

type:
	mypy src

test:
	pytest -q

check: lint type test

all: install check
