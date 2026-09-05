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

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

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

# Build stamp: pass --build-arg BUILD_TIME=... or default to UTC now at build.
# Dockerfile cannot ENV=now(); stamp is written to /etc/arles-build-time for the API.
ARG BUILD_TIME=
RUN stamp="$BUILD_TIME"; \
    if [ -z "$stamp" ]; then stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"; fi; \
    printf '%s' "$stamp" > /etc/arles-build-time

# gp_wrapper.GooglePhotos() defaults to ./client_secrets.json under WORKDIR.
# Mount credentials at runtime (see docker-compose.yml). Do not bake secrets into the image.
# JobStore is in-memory: run a single uvicorn worker.
# ffmpeg: required by moviepy for WMV→mp4 browser preview sidecars.

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
