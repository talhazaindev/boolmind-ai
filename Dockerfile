# Boolmind AI Advisor — production API (CPU). Embeddings use local BGE; FIDP defaults to mock.
# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./

# CPU image: docker-cpu extra forks torch to pytorch-cpu index (no CUDA wheels)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra docker-cpu --no-extra fidp --no-extra gpu

COPY app ./app
COPY main.py ./
COPY frontend ./frontend
COPY knowledge ./knowledge
COPY knowledge-base ./knowledge-base
COPY scripts ./scripts

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra docker-cpu --no-extra fidp --no-extra gpu

# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/data/huggingface \
    FIDP_OUTPUT_DIR=/data/fidp-output

# libgomp: numpy / sentence-transformers; curl: optional health/debug
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder --chown=app:app /app /app

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin app \
    && mkdir -p /data/huggingface /data/fidp-output \
    && chown -R app:app /app /data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
