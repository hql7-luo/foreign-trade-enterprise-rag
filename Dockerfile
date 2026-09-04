FROM python:3.12.11-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.5
COPY pyproject.toml uv.lock README.md ./
COPY app ./app
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12.11-slim-bookworm AS runtime

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY app ./app
COPY scripts ./scripts
COPY data/demo ./data/demo
RUN mkdir -p /app/data/private /app/data/public-demo-runtime && \
    chown -R app:app /app/data/private /app/data/public-demo-runtime

USER app
EXPOSE 8000
CMD ["python", "-m", "scripts.docker_start"]
