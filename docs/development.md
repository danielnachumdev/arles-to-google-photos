# Development

This monorepo has no CLI product. Contributors run the FastAPI backend and the React UI (or Docker). User-facing install is in [Getting started](getting-started.md). **Internals, job types, and API sketch:** [AGENTS.md](../AGENTS.md).

Do not vendor `gp_wrapper`. Do not commit `client_secrets.json` or other secrets.

## Backend (`services/backend`)

Python 3.9+, managed with [uv](https://docs.astral.sh/uv/). The import package is literally `src` (`uvicorn src.api.app:app`).

```bash
cd services/backend
uv sync                 # runtime only
uv sync --group dev     # pytest, mypy, pylint, typing stubs
APP_ENV=local uv run uvicorn src.api.app:app --reload --port 8000
```

`uv sync` does **not** install the `dev` group by default.

Put `client_secrets.json` in `services/backend/` for local publish. Cloud Run / deploy: set non-empty `GOOGLE_OAUTH_CLIENT_ID` and/or JSON in `GOOGLE_OAUTH_CLIENT_SECRETS` / `GOOGLE_CLIENT_SECRETS_JSON` (no file required). Blank env falls back to the file. `GET /api/auth/config` never returns `client_secret`.

**Tests:**

```bash
cd services/backend
uv run pytest
```

`pythonpath` is `.`. Fixture trees: `tests/fixtures/day1_mini` and `tests/fixtures/day1_arles`.

Typecheck config: `mypy.ini` (`files = src`). Prefer a **single** uvicorn worker: `JobStore` keeps an in-process cache over StateStore + ArtifactStore.

## Frontend (`services/frontend`)

React + Vite + TypeScript. Dev server proxies `/api` → `http://127.0.0.1:8000`.

```bash
cd services/frontend
npm install
npm run dev          # http://localhost:5173
npm test             # vitest
npx tsc -b
```

## Package layout (short)

```
.
├── services/backend/src/
│   ├── export/          # preview, parser, editor, publisher, timestamps, scrape
│   ├── jobs/            # workspace, store, ingest, publish, orchestrator, SSE, persistence
│   └── api/             # FastAPI app, routers, schemas
├── services/frontend/src/
│   ├── pages/           # workbench, albums, jobs, settings
│   ├── components/
│   ├── api/             # HTTP + SSE
│   └── lib/
├── docker-compose.yml
├── docs/                # these guides
└── AGENTS.md
```

Domain classes own HTML / Photos logic. FastAPI is a thin adapter. Cloud vs local is **`APP_ENV`** (default `cloud`; Compose `local`). Album **files**: local `FsArtifactStore` when `APP_ENV=local`; GCS when cloud (`GCS_BUCKET` / `ARTIFACT_BUCKET` required; optional `GCS_PREFIX`). Job **state**: local sqlite when `DATABASE_URL` is blank, otherwise the given URL (`gs://` rejected). Cloud + blank `DATABASE_URL` mirrors `{JOBS_ROOT}/migrator.sqlite` to `{GCS_PREFIX}/migrator.sqlite` (DELETE journal; last-writer-wins; single instance only). Prefer Cloud SQL if you scale out. Json StateStore remains for tests/legacy. With GCS, `JOBS_ROOT` is a local cache the parser and publisher hydrate into. See [Persistence](persistence.md).

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on pull requests, pushes to `main`, and manual dispatch. It calls reusable workflows:

- Backend: `uv sync --frozen --group dev` then `uv run pytest`
- Frontend: `npm ci`, `npm test`, `npx tsc -b`

## Docker

```bash
docker compose up --build -d
```

Backend image: runtime deps only, one uvicorn worker. Frontend: nginx, `/api` proxy, SSE buffering off, unlimited upload body. Volume `jobs-data` → `JOBS_ROOT=/app/data/jobs`.

## Next

- [AGENTS.md](../AGENTS.md) — full agent context (orchestrator, scrape kinds, publish order, conventions)
- [Getting started](getting-started.md)
- [Google Photos access](google-photos.md)
