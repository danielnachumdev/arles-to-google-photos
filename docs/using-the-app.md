# Using the app

The UI is a small desk: import → preview → edit → save → publish. You can switch the interface between English and Hebrew under **Settings**; it does not change how albums are parsed.

## Import

On **New**, **Import from web** is selected by default.

1. **Web (default):** paste the gallery start URL (usually `index.html`). Add extra headers only if the site needs them. Click **Import**. Details: [Web import](web-import.md).
2. **Or upload a folder:** switch to **Or upload an exported album folder**, pick the album directory (`index.html`, `hrimages/`, `imagepages/`), then **Prepare preview**. Large folders are fine. Full steps: [Folder import](folder-import.md).
3. Optionally check **Auto-publish to Photos** before you start (Google sign-in up front; publish begins when preview is ready).

Progress streams while files are sent and parsed. When preview is ready, you land on the album desk (folder) or can open it from **Jobs** / **Saved albums** (web / scrape).

## Preview, edit, save

Check:

- Gallery title
- Gallery description (hidden for multi-index albums)
- Journal heading and paragraphs
- Each photo or video title
- Trip date vs file modified time (folder imports may warn if they disagree)

Click a thumbnail to open a larger preview. **Videos** play in the same dialog (controls + poster) when a browser-playable copy exists; otherwise you will see that the video cannot be played in the browser yet. Titles and order still publish.

**Save** writes your edits on the server. They stay with this preview job. Google Photos is unchanged until you publish.

## Publish

1. Click **Publish** (needs [Google Photos access](google-photos.md)).
2. Sign in in the **browser popup**.
3. A **new upload job** runs. The preview job stays a preview.
4. Open the Google Photos link when the job finishes.

**Publish again** creates another independent Photos album. It does not overwrite the previous one.

## Saved albums vs Jobs

| Page | What it is |
|------|------------|
| **Saved albums** | One card per **gallery title** already imported on this server. Not the live website, and not every historical run. Hide/archive on Jobs does **not** remove the card. |
| **Jobs** | Every non-archived run: web scrape, folder preview, and publish. Use this for progress, logs, cancel, restart, and hide. |

After Docker or the API restarts, reopen galleries from **Saved albums**.

Deleting a saved album removes **server job data only**. Your original folder on disk and any Google Photos album are left alone.

## Same gallery title (overwrite)

Importing a folder whose `.gallerytitle` already exists asks before replacing the stored preview. Overwrite keeps the same job id and does **not** republish Google Photos. You can open the existing album instead.

## Reprocess

| Import | Reprocess does |
|--------|----------------|
| **Folder** | Re-parse the album files **already stored** on the server (same id). |
| **Web** | **Re-download** HTML, photos, captions, and journal from the original URL (confirm first). |

Edits on the current preview are replaced. If you have unsaved or saved manual changes, the UI asks before overwriting. You can also create a **new** album (optional title prefix, default `Reprocessed · `).

Upload jobs cannot be reprocessed. There are no Google tokens on disk.

## Cancel

You can cancel a job that is **pending**, **running**, or **waiting**.

- Pending: it never starts.
- Running: work stops cooperatively; files already saved are kept.
- Waiting (typically a hub waiting on children): **descendants are cancelled too**. The dialog lists them.

Cancel does not delete the job row. Google Photos is not deleted.

## Restart a cancelled run

**Restart** is only available on **cancelled** jobs. It creates a **new** job (new id and number). The old row stays cancelled.

For a cancelled **hub** (or other scrape with children), the UI can offer:

| Mode | Meaning |
|------|---------|
| **Restart all** | Dispatch every gallery URL again as new children. |
| **Only remaining / failed** | Skip source children that already finished **done** (matched by scrape URL). Error if every scrape child is already done. |

A leaf scrape ignores “remaining” skip for its preview child (that child is not a scrape child). Restart copies the URL, extra headers, and auto-publish flag — not a Google token. Upload restart reuses the browser Photos session, or prompts if it expired.

## Settings

- **Language** — English or Hebrew (UI only).
- **Max concurrent jobs** — how many jobs may **run** at once (1–32, default **3**). Extra work stays **pending**. **Waiting** parents (a hub blocked on children) do **not** count as running. Raising the cap starts pending jobs immediately; lowering it does not stop jobs that are already running.
- **Clear saved cookies** — drops cached web-import headers from the browser.
- **Sign out of Google Photos** — clears the saved Photos sign-in on this browser. The next publish will ask you to sign in again.

## Next

- [Getting started](getting-started.md)
- [Google Photos access](google-photos.md)
- [Web import](web-import.md)
- [Folder import](folder-import.md)
- [Album layout](album-layout.md)
