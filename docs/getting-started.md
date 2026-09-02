# Getting started

You can run everything with **Docker** (recommended) or start the API and UI yourself on the host.

| | URL |
|---|---|
| App (UI) | [http://localhost:5173](http://localhost:5173) |
| API | [http://localhost:8000](http://localhost:8000) (also proxied as `/api` from the UI) |

Preview (web import or folder upload) works without Google. Publishing needs a Web OAuth client — see [Google Photos access](google-photos.md).

## Docker (easiest)

From the repository root:

```bash
docker compose up --build -d
```

Open [http://localhost:5173](http://localhost:5173). Paste a gallery URL (default) or switch to folder upload, then start the preview.

Compose starts:

- **backend** — FastAPI / uvicorn on port **8000**
- **frontend** — nginx on port **5173**, proxying `/api` to the backend (large uploads allowed; streaming progress is unbuffered)

Stop with `docker compose down`. The named volume `jobs-data` is kept unless you remove it on purpose.

### `client_secrets.json` and Compose

`docker-compose.yml` bind-mounts `./client_secrets.json` into the backend container (read-only) so the UI can load the Google client id.

- **Publish:** put a real Web OAuth JSON at the **repo root**, named `client_secrets.json`. Do not commit it (it is gitignored).
- **Preview only:** if the file is missing, Compose will refuse to start. Either comment out that volume in `docker-compose.yml`, or add a dummy JSON file. Sign-in will fail until you add a real client.
- **Cloud Run:** do not mount a file. Set non-empty `GOOGLE_OAUTH_CLIENT_ID` and/or full JSON in `GOOGLE_OAUTH_CLIENT_SECRETS` / `GOOGLE_CLIENT_SECRETS_JSON` (Secret Manager). Blank env falls back to the file. Details: [Google Photos access](google-photos.md).

A second copy under `services/backend/` is only needed when you run uvicorn on the host (see below).

### Where albums are stored (Docker)

| What | Where |
|------|--------|
| Album folders on your PC | Stay on your PC. Compose does **not** mount `./data` as a source. The browser uploads the folder you pick. |
| Imported files + job state | Docker volume **`jobs-data`** → `/app/data/jobs` inside the backend (`JOBS_ROOT`) |
| Database (default) | `{JOBS_ROOT}/migrator.sqlite` (blank `DATABASE_URL`) |

Recreating containers does not wipe `jobs-data`. Deleting the volume does.

### Cloud Run / remote persistence

Compose sets `APP_ENV=local` → **local sqlite + filesystem** on `jobs-data`. Unset / blank `APP_ENV` defaults to **cloud** (Cloud Run / `docker run`). `GCS_BUCKET` / `DATABASE_URL` are addresses, not the switch. Full detail: [Persistence](persistence.md).

| Env | Meaning |
|-----|---------|
| `APP_ENV` | `cloud` (default; aliases `prod`, `production`) or `local` (aliases `dev`, `development`). |
| `DATABASE_URL` | SQLAlchemy URL (Postgres / Cloud SQL, e.g. `postgresql+psycopg://…`). Alias: `SQLALCHEMY_DATABASE_URL`. Blank → `{JOBS_ROOT}/migrator.sqlite`. `gs://` / `gcs://` is rejected (sqlite cannot open GCS). Optional in cloud. |
| `GCS_BUCKET` | Bucket **name**, or `gs://bucket[/prefix]` / `gcs://bucket[/prefix]`. Alias: `ARTIFACT_BUCKET`. **Required** when `APP_ENV` is cloud. Ignored for backend selection when local. |
| `GCS_PREFIX` | Optional object prefix when `GCS_BUCKET` is a name only (default `jobs`). Empty string stores `{job_id}/…` at the bucket root. Sqlite mirror object: `{GCS_PREFIX}/migrator.sqlite`. |
| `JOBS_ROOT` | Still required: local **cache / materialize** directory for parse and publish. |

Auth is [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials) (Cloud Run service account, `GOOGLE_APPLICATION_CREDENTIALS`, or `gcloud auth application-default login`). Do not bake keys into the image.

- **Album files** go to GCS when `APP_ENV` is cloud (`GCS_BUCKET` required).
- **Job metadata:** cloud + blank `DATABASE_URL` mirrors `{JOBS_ROOT}/migrator.sqlite` to `{GCS_PREFIX}/migrator.sqlite` (DELETE journal; last-writer-wins; **one** Cloud Run instance / one uvicorn worker). Set `DATABASE_URL` (Cloud SQL) if you scale out. Do not use GCS FUSE for sqlite.

Google Photos **Web** OAuth for the UI is separate from GCS ADC: on Cloud Run set non-empty `GOOGLE_OAUTH_CLIENT_ID` and/or full JSON in `GOOGLE_OAUTH_CLIENT_SECRETS` / `GOOGLE_CLIENT_SECRETS_JSON` (Secret Manager). No `client_secrets.json` file is required. See [Google Photos access](google-photos.md).

## Host: uvicorn + npm

Use this if you are developing, or you prefer not to use Docker. You need two terminals.

### Backend

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you do not have it. From `services/backend`:

```bash
uv sync
APP_ENV=local uv run uvicorn src.api.app:app --reload --port 8000
```

Put `client_secrets.json` in **`services/backend/`** (the process working directory) before you publish. Alternatively set non-empty `GOOGLE_OAUTH_CLIENT_ID` or full JSON in `GOOGLE_OAUTH_CLIENT_SECRETS` / `GOOGLE_CLIENT_SECRETS_JSON`. Blank env falls back to the file.

Default job storage on the host is **`services/backend/data/jobs`** (`JOBS_ROOT` relative to the current working directory). That folder is local and gitignored.

### Frontend

From `services/frontend`:

```bash
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` to `http://127.0.0.1:8000`.

## After a restart

- **Saved albums** still lists galleries imported on this server.
- **Jobs** still lists every run.
- Jobs that were **running** or **waiting** when the process stopped are marked **failed** (`interrupted`). Pending jobs on disk are not auto-resumed.

## Next

- [Using the app](using-the-app.md) — preview, edit, publish
- [Google Photos access](google-photos.md) — OAuth for publish
- [Web import](web-import.md) — gallery URL (default)
- [Folder import](folder-import.md) — upload a local Arles export
- [Album layout](album-layout.md) — what the folder must look like
- [Persistence](persistence.md) — sqlite, GCS, Cloud SQL
