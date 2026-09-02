FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Install runtime / publish deps only (not the dev group).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    JOBS_ROOT=/app/data/jobs

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
# Alembic scripts live at WORKDIR (not inside the installed wheel).
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic

# gp_wrapper.GooglePhotos() defaults to ./client_secrets.json under WORKDIR.
# Mount credentials at runtime (see docker-compose.yml). Do not bake secrets into the image.
# JobStore is in-memory: run a single uvicorn worker.

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
