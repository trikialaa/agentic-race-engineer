.PHONY: install test lint typecheck run run-headless fixture evals

install:
	pip install -r requirements.txt -r requirements-dev.txt
	npm ci

test:
	pytest --cov=src --cov-report=term-missing -v

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy src/mcp/functions src/udp_parser

run:
	python main.py

run-headless:
	python -m src.web.web_transcribe_server

fixture:
	python tests/fixtures/build_fixture.py

evals:
	python -m evals.runner
