# ── base: shared runtime deps ──────────────────────────────────────────────
FROM python:3.11-slim@sha256:b27df5841f3355e9473f9a516d38a6783b6c8dfeacaf2d14a240f443b368ddb6 AS base

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── dev: adds dev/test tooling ─────────────────────────────────────────────
FROM base AS dev

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY src/ src/
COPY config.json .
COPY pyproject.toml .

# ── test: runs the full test suite ─────────────────────────────────────────
FROM dev AS test

COPY tests/ tests/

CMD ["pytest", "--cov=src", "--cov-report=term-missing", "-v"]

# ── prod: minimal headless Flask + MCP image ──────────────────────────────
FROM base AS prod

COPY src/ src/
COPY config.json .

RUN useradd --no-create-home --shell /bin/false appuser
USER appuser

EXPOSE 8080

CMD ["python", "-m", "src.web.web_transcribe_server"]
