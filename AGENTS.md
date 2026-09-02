# Arles Migrator – Agent Context

## Project overview

This monorepo migrates **Arles HTML album exports** into Google Photos. **No CLI.** User-facing docs live in [`docs/`](docs/).

- **`services/backend`** — FastAPI job API (`src.api.app:app` on `:8000`). Parses `index.html` / per-image HTML pages, materializes uploads, preview/edits (including journal), stamps capture times, and publishes via [`gp_wrapper`](../gp_wrapper/). Package root: `services/backend/`. Import package is literally `src` (`uvicorn src.api.app:app`). Managed with **uv** + `pyproject.toml`.
- **`services/frontend`** — React + Vite + TypeScript UI (`:5173`). **New** import desk (Arles URL default, or folder upload) → SSE preview → edits → publish. **Saved albums** (`/albums`) is one card per gallery title already on this server (not the live site, not every run; independent of job hide/archive). **Jobs** (`/jobs`) lists every non-archived run (hide/archive finished runs from the list). Reprocess: folder albums reparse stored files; web albums re-download from the original URL (confirm first).
- **Root `docker-compose.yml`** — uvicorn backend + nginx frontend (`/api` proxy, SSE-friendly, unlimited upload body).

Do not commit `client_secrets.json` or other secrets. Do not vendor `gp_uploader`.

## Repository structure

```
.
├── .github/
│   └── workflows/           # CI orchestrator + per-service reusable workflows
├── services/
│   ├── backend/
│   │   ├── src/
│   │   │   ├── __init__.py
│   │   │   ├── utils.py             # batchify
│   │   │   ├── progress.py          # ProgressSink protocol
│   │   │   ├── export/              # preview, parser, editor, publisher, timestamps
│   │   │   ├── jobs/                # workspace, store, ingest, publish, SSE bus, persistence/
│   │   │   └── api/                 # FastAPI composition root + routers
│   │   │       ├── app.py           # create_app: store/services, CORS, include_router; `app = create_app()`
│   │   │       ├── schemas.py       # JournalBody, PreviewEditBody, PublishBody
│   │   │       ├── deps.py          # ApiDependencies on app.state
│   │   │       └── routers/         # jobs CRUD/media/reprocess, publish, auth config, SSE + history
│   │   ├── tests/
│   │   │   └── fixtures/            # day1_mini, day1_arles
│   │   ├── pyproject.toml
│   │   ├── uv.lock
│   │   ├── mypy.ini
│   │   └── Dockerfile
│   └── frontend/
│       ├── src/                     # App + pages/, components/, lib/, api/, storage/
│       ├── nginx.conf               # /api → backend:8000 + SPA fallback; client_max_body_size 0
│       └── Dockerfile
├── data/                            # Local album folders (gitignored). NOT docker-mounted as source.
├── docker-compose.yml               # client_secrets.json + jobs-data only
├── docs/                            # User-facing guides (README links here)
├── README.md                        # Landing page; details in docs/
├── client_secrets.json              # Google OAuth (do not commit); repo-root copy for compose
└── AGENTS.md
```

Also put `client_secrets.json` in `services/backend/` for host uvicorn (CWD for `GooglePhotos()`).

## Expected album folder layout (Arles)

Each album directory must look like the old Arles HTML export:

```
ALBUM_FOLDER/
├── index.html               # Required. Gallery title, optional gallery description, journal, thumbnail grid
├── index1.html, …           # Optional. Multiple index*.html → “multi-index”; gallery description skipped
├── hrimages/                # Required. High-res files (e.g. 20120802_01hr.JPG)
└── imagepages/
    └── 20120802_01.html     # Per-image page; `.imagetitle` used as Google Photos image title
```

**Filename mapping:** strip a **trailing** `hr` from the HR stem (case-insensitive). Example: `hrimages/20120802_01hr.JPG` → id `20120802_01` → `imagepages/20120802_01.html`. Do **not** strip a leading `hr`. Do **not** use `str.replace("hr", "")`.

**Gallery membership + order:** only photos linked from the `index*.html` thumbnail grids (`a[href=imagepages/ID.html]`), in index ordinal order (`index.html` / `index1` → `index2` → …) — **not** a filesystem sort of `hrimages/`. Folder exports keep sibling `index2.html` on disk and the parser merges their grids; web scrape merges siblings into `index.html` before parse. Decoys such as `Text.jpg` / `aaa.jpg` are excluded if they are not on any index grid.

**Gallery title / gallery description:** `.gallerytitle` / `.gallerydesc` spans. `.gallerydesc` is often empty. Multi-index skips gallery description.

**Journal:** Word HTML `div.WordSection1` at the bottom of `index.html` (e.g. heading `יומן`). Parsed as `AlbumJournal` (heading + paragraphs), editable via PATCH, shown in the UI. On publish, a non-empty **heading** is its own Photos **text enrichment** (Google Photos centers short text ≈ title). Non-empty **paragraphs** are a second enrichment (blank-line separated). Both use `Album.add_text(..., FIRST_IN_ALBUM)`. Empty journal (missing, blank heading, no paragraphs) is skipped. Call order: gallery description (if any) → journal body (if any) → journal heading (if any), so visual top→bottom is heading, body, description, photos. Gallery description ≠ journal.

**`taken_on`:** parsed from the `YYYYMMDD` prefix of the item id (trip date), **not** EXIF and not filesystem mtime. `last_modified` is FS / browser `File.lastModified`.

**Publish timestamps:** before upload, `CaptureTimestampStamper` (`src/export/timestamps.py`) writes capture time to JPEG EXIF (`DateTimeOriginal` / Digitised / DateTime) and FileTime atime/mtime (Google Photos uses EXIF). Keeps existing camera EXIF if it already increases in gallery order; bumps by 1s if out of order; if no EXIF, uses `taken_on` at midnight + gallery index seconds. Runtime dep: `piexif>=1.1.3`.

**Album order:** text enrichments first (`FIRST_IN_ALBUM`: journal heading, then journal body, then optional gallery description). Photos: `MediaItem.batchCreate` with `AlbumPosition(LAST_IN_ALBUM)` then subsequent batches `AFTER_MEDIA_ITEM` after the last created id, so Photos album custom order matches gallery order.

## Tech stack

- **Backend language:** Python 3.9+ preferred
- **Backend toolchain:** [uv](https://docs.astral.sh/uv/) + `pyproject.toml` / `uv.lock`
- **Backend runtime:** `[project].dependencies` — `gp_wrapper>=0.9.12`, `beautifulsoup4`, `tqdm`, `fastapi`, `uvicorn`, `python-multipart`, `piexif>=1.1.3`, `google-cloud-storage>=2.14.0`, `sqlalchemy>=2.0.25`, `psycopg[binary]`, `alembic`
- **Schema migrations:** Alembic under `services/backend/alembic/` (`alembic.ini` + declarative models in `src/jobs/persistence/models.py`). `SqlAlchemyStateStore` construction runs `migrate.upgrade_head` (fail closed). Same URL as the app (`DATABASE_URL` / local `{JOBS_ROOT}/migrator.sqlite`). Manual: `uv run alembic upgrade head` from `services/backend`. Do not use ad-hoc `ALTER TABLE` / `create_all` for new columns — add a revision.
- **Backend dev:** `[dependency-groups].dev` — mypy, pylint, pytest, pytest-cov, pytest-xdist, httpx, typing stubs
- **Lock constraint:** `tool.uv.constraint-dependencies` pins `moviepy>=1.0.3,<2` because gp_wrapper imports `moviepy.editor` (removed in moviepy 2.x)
- **gp_wrapper 0.9.12+:** portable `FileTimeService` (no Win32 ctypes). Non-mp4 video transcode runs with or without `pbar`, copies source access/modification onto the local `.mp4`, and embeds MP4 `creation_time` (Photos dates videos from container metadata). `Dictable` serializes Enums (e.g. `PositionType`) so `AlbumPosition.to_dict()` is JSON-safe. `uv.lock` pins `gp-wrapper==0.9.12`.
- **Auth:** Google Photos Library API. **Web** OAuth client from env (Cloud Run / Secret Manager) or local `client_secrets.json`. Precedence: non-empty `GOOGLE_OAUTH_CLIENT_ID` → non-empty JSON in `GOOGLE_OAUTH_CLIENT_SECRETS` or `GOOGLE_CLIENT_SECRETS_JSON` (same shape as the file) → file at `GOOGLE_CLIENT_SECRETS` or `./client_secrets.json`. Blank env is treated as absent (file fallback). Frontend GIS requests Photos scopes (`photoslibrary`, `appendonly`, `sharing`, `edit.appcreateddata`); the browser stores the access token + expiry in **localStorage** only (`arles.googlePhotos.session`) and reuses it across reloads/albums/publish until it expires or Google returns 401. GIS popup uses a silent/empty prompt when a session exists; interactive consent only when missing/expired/401. Settings can clear the browser session. `POST /api/jobs/{id}/publish` sends `{ "access_token" }`. Backend builds `AccessTokenGooglePhotos` (no `run_local_server()`). Backend must **not** persist Photos tokens. `GET /api/auth/config` returns `{ client_id, scopes }` only (never `client_secret`). JS origins: `http://localhost:5173` and `http://127.0.0.1:5173`. Consent screen must list the signed-in Google account as a test user.
- **Frontend:** React + Vite + TypeScript; Vitest + jsdom. Dev proxy `/api` → `127.0.0.1:8000`.
- **Containers:** backend image runtime deps only, **single** uvicorn worker (`JobStore` keeps an in-process cache over StateStore + ArtifactStore). Frontend nginx proxies `/api`, disables buffering for SSE, `client_max_body_size 0`. `JOBS_ROOT=/app/data/jobs` on volume `jobs-data` (uploaded albums + job state across recreates). Cloud vs local is **`APP_ENV`** (default **`cloud`** when unset/blank; aliases `prod`/`production`. `local` aliases `dev`/`development`). Compose sets `APP_ENV=local`. `GCS_BUCKET` / `DATABASE_URL` are resource addresses, not the detector. **`APP_ENV=local`:** `FsArtifactStore` on `{JOBS_ROOT}` + local sqlite (or json); ignore bucket for backend selection. **`APP_ENV=cloud`:** `GcsArtifactStore` (`GCS_BUCKET` / `ARTIFACT_BUCKET` required — name or `gs://bucket[/prefix]` / `gcs://bucket[/prefix]`); optional `GCS_PREFIX` (default `jobs`); `DATABASE_URL` (alias `SQLALCHEMY_DATABASE_URL`) optional (Postgres / Cloud SQL); if unset → local sqlite **plus** GCS sqlite mirror `{GCS_PREFIX}/migrator.sqlite` (DELETE journal, last-writer-wins; background upload at most once per second so API writes do not block on GCS; **one** Cloud Run instance / one uvicorn worker — prefer Cloud SQL if you scale out; do not use GCS FUSE). `gs://` / `gcs://` `DATABASE_URL` is rejected. `JOBS_ROOT` is still the **local hydrate/cache** so parser/publisher get a `Path`. Auth: Application Default Credentials (Cloud Run SA, `GOOGLE_APPLICATION_CREDENTIALS`, or `gcloud auth application-default login`) — do not bake keys. Host uvicorn: set `APP_ENV=local` (default `JOBS_ROOT` is `data/jobs` relative to CWD). Compose does **not** mount `./data` as album source; the user picks a folder in the browser and files are uploaded.

## Setup (backend)

From `services/backend`:

```bash
cd services/backend
uv sync                 # runtime / publish only → .venv
uv sync --group dev     # also mypy, pylint, pytest, typing stubs
```

`tool.uv.default-groups` is empty so `uv sync` does **not** install the `dev` group by default.

`GET /api/auth/config` reads the **Web** OAuth `client_id` (never the secret). **Local / Compose:** `./client_secrets.json` (CWD) or path in `GOOGLE_CLIENT_SECRETS`; compose mounts the repo-root file. **Cloud Run:** set non-empty `GOOGLE_OAUTH_CLIENT_ID` and/or full JSON in `GOOGLE_OAUTH_CLIENT_SECRETS` / `GOOGLE_CLIENT_SECRETS_JSON` (Secret Manager); no file required. Blank env falls back to the file. Put `client_secrets.json` in `services/backend/` for host uvicorn (gitignored via `*client_secret*`). Do not commit either copy.

## Running / entry points

- **API (cwd = `services/backend`):** `APP_ENV=local uv run uvicorn src.api.app:app --reload --port 8000`
- **Frontend:** `npm install` then `npm run dev` in `services/frontend` → http://localhost:5173
- **Docker:** `docker compose up --build -d` → UI http://localhost:5173, API http://localhost:8000. Ingest/preview/publish work; Google sign-in is in the browser. Mount `./client_secrets.json` must exist on host or comment out that volume.

Flow: paste gallery URL (default) or pick album folder → Import / Prepare preview (SSE ingest; default phase closes on `preview_ready`) → verify/edit gallery title, gallery description, journal, image titles → Save → Publish (Google sign-in in the **UI** once per browser session, then a **new upload job**) → album URL. Publish SSE: `/api/jobs/{uploadId}/events?phase=publish` closes on `done`/`error`. The preview job stays `type=preview`. After restart, **Saved albums** reopens imported galleries; **Jobs** lists every run. Reprocess folder albums from stored files; reprocess web albums / scrape jobs re-downloads from the original URL after confirm. Same gallery title asks before overwriting the stored preview (does not republish Google Photos).

## API sketch

Job types: `preview` | `upload` | `scrape`. Lineage: `source_job_id` = upload←preview artifact share; `parent_job_id` = scrape tree (child preview / child scrape). Children are not stored as a column; `GET` computes `child_ids`.

- `POST /api/jobs` multipart `files` + optional `lastModified` (ms, parallel to files) + query `overwrite` (default `false`). Creates a **pending** preview and returns **201 immediately**; ingest runs via the orchestrator. Same `.gallerytitle` without overwrite → **409** `{ "detail": { "code": "album_exists", "existing_id": "...", "title": "..." } }`. `?overwrite=true` folds into that job (keeps id / `created_at` / `product_url`)
- `POST /api/jobs/scrape` JSON `{ "url", "headers"? }` → **201 scrape job** (pending until a worker slot is free). Persists url + headers for retry; API never returns header **values** (`has_headers` + `header_names` only). Subscribe to `/api/jobs/{id}/events?phase=scrape` (stages: `scrape`, `child`, `preview_ready`, `waiting`, `done`, `error`). Page kinds: **leaf** (photo grid), **parent** (Arles `BeginSubCategories`), **hub** (non-Arles album list: ≥2 one-level `*/index.html` links, no `imagepages/` grid; e.g. Mso bilingual trip index). PARENT/HUB return child gallery URLs only; a top-level scrape **enqueues** one child scrape per URL (pending, not inline). Dummy preview on hub/parent is discarded, not failed. Preview parse runs inside the scrape worker (does not consume a second slot). After the parent's own work, if any descendant is still `pending|running|waiting`, the parent becomes **`waiting`** (not `done`). It finishes only when every descendant is terminal. If any child **failed**, the parent is **`done` with `warnings`** (not `failed`); cancelled children are terminal and do not fail the parent. Parent's own failure stays `failed`.
- `GET /api/jobs` → `{ "jobs": [ summary… ] }` newest-first, **every non-archived run** (preview + upload + scrape). `?dedupe=true` → one row per gallery title (**Saved albums**: preview/upload with a real title; scrape-only hostname rows omitted). Dedupe **ignores** `archived_at` so hiding a run does not remove the gallery card. `?include_archived=true` includes soft-deleted runs on the **jobs** list only (not required for Saved albums). Summaries include `archived_at` (null if not archived).
- `GET /api/jobs/{id}` full job including preview, `scrape_url`, `parent_job_id`, `child_ids`, `has_headers` / `header_names` (`source_job_id` on upload runs), optional `warnings`, `import_origin` (`folder` | `web`), `archived_at`
- `POST /api/jobs/{id}/archive` → **200** `{ job, archived_ids }` soft-delete (sets `archived_at`). Terminal only (`done`/`failed`/`cancelled`); **409** if the job or any descendant is `pending`/`running`/`waiting` (cancel first). Cascades to descendants. Artifacts stay. `GET /api/jobs/{id}` still works.
- `GET /api/jobs/{id}/children` → `{ "jobs": [ summaries… ] }` direct children only
- `PATCH /api/jobs/{id}` title, description, journal `{heading, paragraphs}`, captions (status `done` / type `preview`, keeps `product_url`)
- `POST /api/jobs/{id}/reprocess` **folder preview**: reparse stored album files (same id). **Web preview child**: retry the parent **leaf** scrape (re-download HTML / hr images / captions / journal from persisted `scrape_url` + headers; same preview id; do not retry a hub). **Scrape job**: `retry()` same id (re-download). 409 on upload. No Google tokens on disk.
- `GET /api/jobs/{id}/restart-preview` → `{ job, descendants, done, remaining }` scrape children of a **cancelled** job (404 missing, 409 if not cancelled). Preview children are omitted. Used by the UI to choose All vs Remaining.
- `POST /api/jobs/{id}/restart` JSON `{ "access_token"?, "mode"?: "all"|"remaining" }` → **201 new job** from a **cancelled** run (409 otherwise, 404 if missing). Default **`all`**. New UUID + number, status **pending**, enqueued via orchestrator. Old job stays cancelled. Scrape: copy url/headers/`auto_publish` (no stored Google token). **`all`**: hub dispatches every gallery URL as **new** children. **`remaining`**: persist `skip_done_urls` on the new job and skip source children whose status is **`done`** (match by `scrape_url`); 400 if every scrape child is already done. Leaf scrape ignores remaining-mode skip (preview child is not a scrape child). Preview: copy artifact tree, parse from scratch. Upload: `create_upload_from` + token required (401 if missing). Not same-id reprocess/retry.
- `GET /api/auth/config` → `{ "client_id", "scopes" }` (503 if no non-empty env and no readable `client_secrets.json`)
- `POST /api/jobs/{id}/publish` JSON `{ "access_token" }` → **201 new upload job** (pending until a slot is free; source preview/upload is unchanged). Subscribe to `/api/jobs/{uploadId}/events?phase=publish`. 401 if blank token; Google sign-in is in the UI
- `GET /api/settings` → `{ max_concurrent_jobs, pending, running, waiting }`. `PATCH /api/settings` `{ max_concurrent_jobs }` (int 1–32, persisted in SQLAlchemy `meta` or `{JOBS_ROOT}/meta.json`). Default cap **3**. Raising the cap starts pending jobs immediately; lowering does not kill running jobs.
- `GET /api/jobs/{id}/events?phase=ingest|publish|scrape`
- `GET /api/jobs/{id}/history` → `{ "events": [ { job_id, stage, message, current, total, extra, occurred_at } ] }` (StateStore: SQLAlchemy `events` table or json `events.json`)
- `GET /api/jobs/{id}/media/{itemId}` thumbnail/original

Preview JSON includes `journal`, `taken_on` (ISO date or null), `last_modified`, `multi_index`, items in gallery order. Job detail/summary also include `created_at` (ISO enqueue time), `started_at` (first transition to `running`, else null), `running_started_at` (open running interval, else null), `duration_seconds` (time spent **`running` only** — pending queue wait and `waiting` are excluded; live while running; `0` if cancelled before start; legacy terminal rows without run timing still use last-event minus `created_at`), optional `folder_label`, and `import_origin` (`folder` local upload vs `web` scrape). Folder ingest → `folder`; scrape jobs and preview children → `web`. Restart/reprocess/overwrite copy origin. Legacy rows without the field infer `web` if `parent_job_id`, `type == scrape`, or `scrape_url` is set, else `folder`. UI taken_on/mtime mismatch warning is folder-only.

**Job statuses:** `pending` | `running` | `waiting` | `done` | `failed` | `cancelled`. `waiting` is not terminal (`finished_at` unset) and is not counted as running. Cancel is allowed on pending/running/waiting; restart only on cancelled. Archive (soft delete) is allowed on terminal jobs only; the jobs list omits archived rows. Saved albums (`?dedupe=true`) still include them — job runs and album cards are independent.

**Job orchestrator:** in-process FIFO (`src/jobs/orchestrator.py`) with three queues: **pending**, **running**, **waiting**. `max_concurrent_jobs` applies **only to running**. Waiting jobs (own work finished, blocked on descendants) do not occupy a slot. All ingest/scrape/publish/reprocess/restart/auto-publish work goes through `submit`. Cancel of **pending** drops the queue entry so `fn` never runs; cancel of **running** is cooperative and frees the slot on exit; cancel of **waiting** cascade-cancels descendants. On process start, leftover **running** and **waiting** jobs are marked **failed** (`interrupted`); pending jobs on disk are **not** auto-resumed (no persisted work closure). Still use **one uvicorn worker**.

**Durable history:** `JobStore.load(JOBS_ROOT)` hydrates from StateStore. SQLAlchemy sqlite migrates leftover `{id}/job.json` (+ `events.json`) on first open and then is source of truth for state (artifact trees stay on disk for fs, or in GCS with a local cache). When `APP_ENV` is cloud and `DATABASE_URL` is blank, `migrator.sqlite` is downloaded from `{GCS_PREFIX}/migrator.sqlite` on open and uploaded after metadata writes. Json backend still scans `job.json` (tests / legacy). Corrupt records are skipped. Still use **one uvicorn worker** (in-memory cache is not shared). On Cloud Run (ephemeral disk, `APP_ENV` unset or `cloud`): `GCS_BUCKET` for album files; blank `DATABASE_URL` + bucket mirrors sqlite (single instance); set `DATABASE_URL` (Cloud SQL) if you scale out.

## Tests

- **Backend:** from `services/backend`, `uv run pytest` (pythonpath `.`; quiet + `-n auto` + `src` coverage with missing lines). Fixture trees: `tests/fixtures/day1_mini` and `tests/fixtures/day1_arles`.
- **Frontend:** from `services/frontend`, `npm test` (vitest) and `npx tsc -b`.
- **CI:** GitHub Actions (`.github/workflows/ci.yml`) runs on pull requests and pushes to `main`. It delegates to per-service reusable workflows: backend `uv run pytest`, frontend `npm test` + `npx tsc -b`.

## Code conventions

- Type checking: `services/backend/mypy.ini` (`disallow_untyped_calls`, `check_untyped_defs`, `no_implicit_optional`; `files = src`)
- Lint: pylint (enabled in `.vscode/settings.json`)
- Format: autopep8 on save
- Domain classes own HTML/Photos logic; FastAPI is a thin adapter; `JobStore` is a facade over StateStore + ArtifactStore with an in-process cache (do not run multiple uvicorn workers)
- TDD for new classes; `/async` only on disjoint files (never parallel `pyproject.toml` / `uv.lock` / `App.tsx` / compose)

## Important files

| Path | Purpose |
|------|--------|
| `services/backend/src/export/` | Preview models, parser, editor, publisher |
| `services/backend/src/export/timestamps.py` | `CaptureTimestampStamper` (JPEG EXIF + FileTime before upload) |
| `services/backend/src/jobs/` | Workspace, JobStore facade, ingest, reprocess, restart, publish, orchestrator, SSE |
| `services/backend/src/jobs/orchestrator.py` | FIFO pending/running/waiting queues; `max_concurrent` only on running (default 3) |
| `services/backend/src/jobs/persistence/` | StateStore (SQLAlchemy sqlite/postgres + json) + ArtifactStore (`fs` + `gcs`); Alembic schema (`models.py` + `migrate.py` + `alembic/`); selected by `APP_ENV` (`cloud` default, compose `local`); album files never in the DB; cloud uses `GCS_BUCKET` + optional `DATABASE_URL` (sqlite mirrored to `{prefix}/migrator.sqlite` when URL unset, background ≤1/s); `meta` / `meta.json` for orchestrator cap |
| `services/backend/src/api/google_oauth.py` | `load_google_oauth_client_id`: env then JSON env then `client_secrets.json` |
| `services/backend/src/api/app.py` | FastAPI `create_app` (composition root; `include_router`) |
| `services/backend/src/api/routers/` | HTTP adapters: jobs CRUD/media/reprocess/restart, publish, SSE + history, settings |
| `services/backend/src/api/routers/settings.py` | GET/PATCH `/api/settings` (`max_concurrent_jobs`) |
| `services/backend/src/api/schemas.py` | Pydantic request bodies |
| `services/backend/src/api/deps.py` | `app.state` accessors (`ApiDependencies`) |
| `services/backend/tests/fixtures/day1_arles/` | Arles-shaped fixture (trailing-`hr` names, decoys, journal) |
| `services/backend/tests/fixtures/day1_mini/` | Smaller parser/API fixture |
| `services/backend/pyproject.toml` | uv project; runtime deps (incl. `piexif>=1.1.3`) + `dev` group |
| `services/backend/uv.lock` | Lockfile (commit this; do not gitignore) |
| `services/frontend/src/pages/AlbumWorkbench.tsx` | Folder picker, history, preview desk, reprocess, publish |
| `services/frontend/nginx.conf` | `/api` proxy, SSE (`proxy_buffering off`), unlimited body |
| `docker-compose.yml` | uvicorn + nginx stack; `client_secrets.json` + `jobs-data` |
| `.github/workflows/ci.yml` | CI orchestrator; calls per-service reusable test workflows |
| `README.md` | Short landing page; details in `docs/` |
| `docs/` | Getting started, OAuth, album layout, web import, using the app, persistence, development |

## Sensitive / ignored files

Do not commit or suggest adding:

- **Secrets:** `client_secrets.json`, `*client_secret*`, `.pypirc`
- **Local data:** `data/`, `*.zip`, `tmp.py`
- **Environments:** `.venv`, `venv/`, `.env`
- **IDE/cache:** `.idea/`, `__pycache__/`, `.mypy_cache/`

Do **not** gitignore `pyproject.toml` or `uv.lock`. See `.gitignore` for the full list.
