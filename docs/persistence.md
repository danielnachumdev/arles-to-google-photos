# Persistence

Job **metadata** (status, preview JSON, events, orchestrator cap) and album **files** are stored separately. Cloud vs local is **`APP_ENV`**, not `STATE_BACKEND` / `ARTIFACT_BACKEND` and not bucket blankness. Unset / blank `APP_ENV` → **cloud**. Compose sets `APP_ENV=local`. `GCS_BUCKET` / `DATABASE_URL` are resource addresses.

## Local (`APP_ENV=local` — Compose / host uvicorn)

| What | Where |
|------|--------|
| Album files | `{JOBS_ROOT}/{job_id}/` (`FsArtifactStore`) |
| Job metadata | `{JOBS_ROOT}/migrator.sqlite` (blank `DATABASE_URL`) |

Compose volume `jobs-data` keeps both across container recreates. Sqlite uses WAL journal locally. A set `GCS_BUCKET` is **ignored** for backend selection.

## Cloud Run (`APP_ENV` unset or `cloud` / `prod` / `production`)

`JOBS_ROOT` is a **hydrate/cache** only. It does not survive instance recreates.

| Env | Role |
|-----|------|
| `GCS_BUCKET` / `ARTIFACT_BUCKET` | **Required.** Album **files** in GCS (`GcsArtifactStore`). Prefix: URI path, or `GCS_PREFIX` (default `jobs`), or empty string for `{job_id}/…` at the bucket root. |
| Blank `DATABASE_URL` | Local sqlite still used at `{JOBS_ROOT}/migrator.sqlite`, and the file is **mirrored** to GCS object **`{GCS_PREFIX}/migrator.sqlite`** (or `migrator.sqlite` when the prefix is empty). |
| `DATABASE_URL` (Postgres / Cloud SQL) | Optional. Remote SQLAlchemy metadata. Sqlite is **not** synced to GCS. Use this when you scale out. |

Auth for GCS is [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials) (Cloud Run SA, `GOOGLE_APPLICATION_CREDENTIALS`, or `gcloud auth application-default login`). Do not bake keys.

### Sqlite + GCS mirror

SQLite **cannot** open `gs://` / `gcs://`. Setting `DATABASE_URL` to a GCS URI fails at startup.

When the mirror is on:

1. On StateStore open: download `{GCS_PREFIX}/migrator.sqlite` into `{JOBS_ROOT}/migrator.sqlite` if the object exists.
2. After metadata writes (create / save / delete / events / meta): upload that sqlite file back to the same object.
3. Journal mode is **DELETE** (not WAL), so `-wal` / `-shm` sidecars do not need to be synced.

**Concurrency:** last-writer-wins. Safe only with **one** Cloud Run instance and **one** uvicorn worker. Do **not** mount the bucket with GCS FUSE and point sqlite at the mount — that is unsafe with multiple instances. Prefer `DATABASE_URL` (Cloud SQL) if `max_instance_count` > 1.

`job.json` / `events.json` are **not** uploaded to GCS (legacy json StateStore / local cache only).

### GCS as staging (not Google Photos)

Album bytes stage in the artifact store **before** Google Photos:

1. **Ingest** — folder multipart and scrape HR downloads stream **one file at a time** into the store (`put_file` / `materialize_album_tree`). Cloud scratch keeps media as **sparse placeholders** after upload; HTML/structure stays local for parse.
2. **Preview / edit** — UI and media routes prefer **thumbnails** (and short derived video posters). Opening the desk must not auto-hydrate multi‑GiB `hrimages/` / full `play` bodies into the instance.
3. **Publish** — serial streamed upload to Photos (`/v1/uploads`); local hydrate + remux companions are released after each item. Per-item checkpoints live on the upload job’s `extra` so a crash can resume without re-uploading completed items.
4. **Size class** — `large` when any media file is **> 256 MiB** or total media **> 1 GiB** (else `small`). Folder import uses browser `File.size`; scrape probes `Content-Length` via HEAD when available, otherwise measures on download. A single file above the hard ceiling (**1.5 GiB** on 2 GiB Cloud Run) is rejected/warned until streaming+disk policy is proven for that size.

Do **not** use Google Photos as a draft/staging library.

## Env summary

| Env | Meaning |
|-----|---------|
| `APP_ENV` | `cloud` (default; aliases `prod`, `production`) or `local` (aliases `dev`, `development`). Compose sets `local`. |
| `DATABASE_URL` | SQLAlchemy URL. Alias: `SQLALCHEMY_DATABASE_URL`. Blank → local sqlite. `gs://` / `gcs://` rejected. Optional in cloud. |
| `GCS_BUCKET` | Bucket name or `gs://bucket[/prefix]` / `gcs://bucket[/prefix]`. Alias: `ARTIFACT_BUCKET`. Required in cloud; ignored for backend selection when local. |
| `GCS_PREFIX` | Object prefix when `GCS_BUCKET` is a name only (default `jobs`). |
| `JOBS_ROOT` | Local cache / materialize directory (always required). |
