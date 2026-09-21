# Build context is the repo root (uv workspace), e.g.:
#   docker build -f apps/api/Dockerfile -t reimburse-api .
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/
ENV UV_PYTHON_DOWNLOADS=0 UV_COMPILE_BYTECODE=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/api apps/api
COPY apps/worker apps/worker
COPY py/shared py/shared

RUN uv sync --frozen --no-dev --package api

WORKDIR /app/apps/api
ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
