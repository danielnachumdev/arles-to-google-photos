# Arles → Google Photos

Turn an old [Arles](https://www.digitaldutch.com/arles/) HTML album into a Google Photos album — same order, titles, journal, and trip dates.

[Arles Image Web Page Creator](https://www.digitaldutch.com/arles/) (Digital Dutch) builds offline galleries: `index.html`, thumbnails, high-res files, and a page per photo. This app reads a **live gallery URL** (default) or an exported folder, lets you check a preview, and publishes to Google Photos.

No command line required. Docker is the easiest path.

## Try it in 60 seconds

```bash
docker compose up --build -d
```

Open [http://localhost:5173](http://localhost:5173) → paste a gallery URL → **Import**.

Or upload a local Arles export: switch to folder import, pick the album folder → **Prepare preview**.

Preview does not need Google. Publish does: a popup in the **browser** (not a terminal). One-time setup: [Google Photos access](docs/google-photos.md).

If Compose complains that `client_secrets.json` is missing, comment out that volume in `docker-compose.yml` or follow the Google Photos guide. More install options: [Getting started](docs/getting-started.md).

## What you get

- Gallery title, optional description, and journal at the top of the Photos album
- Photos and videos in **thumbnail-grid order** (not a filesystem sort)
- Image / video titles from each item’s HTML page
- Trip dates from the `YYYYMMDD` prefix in the item id — not camera EXIF, not “date modified”

## Two ways in

| | How |
|---|---|
| **Web** (default) | Paste a gallery URL. Optional extra headers (for example `Cookie`) if the site needs them. [Web import](docs/web-import.md). |
| **Folder** | Upload a local Arles export from your computer. [Folder import](docs/folder-import.md). |

There is no username/password login for web import — only optional headers.

### Folder layout (when uploading from disk)

```
ALBUM_FOLDER/
├── index.html
├── hrimages/
│   └── 20120802_01hr.JPG
└── imagepages/
    └── 20120802_01.html
```

Required: `index.html` + `hrimages/` + `imagepages/`. Order comes from the thumbnail grid, not a filesystem sort. Trailing-`hr` names, journal, multi-index, and video: [Folder import](docs/folder-import.md) · [Album layout](docs/album-layout.md).

Docker does **not** mount `./data` as a source — you pick the folder in the browser.

## In the app

- **Saved albums** — one card per gallery already on this server (not the live website).
- **Jobs** — every run: preview, scrape, and publish.

How to edit, publish, reprocess, restart, and cancel: [Using the app](docs/using-the-app.md).

## Docs

| Guide | What’s inside |
|-------|----------------|
| [Getting started](docs/getting-started.md) | Docker and local uvicorn + npm |
| [Google Photos](docs/google-photos.md) | OAuth, consent screen, `client_secrets.json` |
| [Web import](docs/web-import.md) | URL scrape, headers, hubs vs leaves (**default import**) |
| [Folder import](docs/folder-import.md) | Upload a local Arles export (UI + required tree) |
| [Album layout](docs/album-layout.md) | Arles folder, journal, videos |
| [Using the app](docs/using-the-app.md) | Preview, publish, reprocess, settings |
| [Persistence](docs/persistence.md) | Sqlite, GCS, Cloud SQL |
| [Development](docs/development.md) | Tests, packages, contributor setup |

## For developers

Local toolchain, tests, and package layout: [docs/development.md](docs/development.md). Internals and API: [AGENTS.md](AGENTS.md).

**CI:** GitHub Actions runs backend tests (`uv run pytest`) and frontend tests (`npm test`, `npx tsc -b`) on pull requests and pushes to `main`.

## License

[PolyForm Noncommercial 1.0.0](LICENSE) — free for personal and other non-commercial use. Commercial use requires a separate license from the copyright holder.
