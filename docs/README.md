# Docs

User guides for **Arles → Google Photos**. The [root README](../README.md) is the short front door; these pages have the detail.

| Guide | Read this when… |
|-------|-----------------|
| [Getting started](getting-started.md) | You want Docker or a local uvicorn + npm install |
| [Google Photos](google-photos.md) | You are ready to **publish** (OAuth, consent screen, `client_secrets.json`) |
| [Web import](web-import.md) | You are importing from a gallery URL (default: headers, unsupported URL, hubs) |
| [Folder import](folder-import.md) | You are uploading a local Arles export (UI steps + required tree) |
| [Album layout](album-layout.md) | Your folder does not look like an Arles export, or titles/order/dates look wrong |
| [Using the app](using-the-app.md) | You want preview → edit → publish, reprocess, restart, cancel, or settings |
| [Persistence](persistence.md) | Local sqlite + fs, GCS album files, sqlite mirror, Cloud SQL |
| [Development](development.md) | You are changing code, running tests, or checking CI |

The in-app UI can be English or Hebrew. These docs are English only.

Contributor internals (job types, orchestrator, parsers): [AGENTS.md](../AGENTS.md).
