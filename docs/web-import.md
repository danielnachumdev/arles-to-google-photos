# Web import

This is the **default** import path. Paste the URL of an existing Arles HTML gallery. The app downloads `index.html`, per-item pages, high-res files, and journal text, then builds the same preview as a folder import.

There is **no username / password form** and **no HTTP Basic Auth** in this app. If the site needs credentials, pass them yourself as **optional extra headers** (most often a `Cookie`).

To upload a local export instead, see [Folder import](folder-import.md).

## Start an import

1. On **New**, **Import from web** is already selected.
2. Paste the gallery start page (usually an `index.html`).
3. Optionally add extra headers (name + value). Example: `Cookie` → your session cookie.
4. Optionally check **Cache headers for next import** (saved in the browser). Clear them later under **Settings**.
5. Optionally check **Auto-publish to Photos** (you sign in when starting; publish begins after preview is ready).
6. Click **Import**. Watch progress on **Jobs**.

The scrape URL (and header *names*, not values) are stored so you can retry or reprocess later.

## Extra headers

Use this only when a plain GET is not enough — for example a site that requires a logged-in cookie.

- Headers are sent with gallery downloads.
- The API remembers that headers were used (`has_headers` + `header_names`) but **does not return header values** in responses.
- Cached headers live in the browser only. **Settings → Clear saved cookies** removes them.

Do not paste secrets into issues or commits.

## What kind of page is this?

| Kind | What it looks like | What happens |
|------|--------------------|----------------|
| **Leaf** | Arles photo grid (`imagepages/…` thumbnails) | Download the album and build a preview |
| **Parent** | Arles subcategory index (`BeginSubCategories` / child gallery links, no photo grid) | Enqueue one **child scrape** per child gallery URL. No dummy album preview is kept. |
| **Hub** | Not a classic Arles index, but a list of at least two one-level `*/index.html` links (no `imagepages/` grid) | Same as parent: child scrapes only |
| **Unknown** | Anything else | Error: not a supported Arles album |

A top-level scrape does **not** download every child album inline. Each child is its own job (pending until a worker slot is free). Preview parsing for a leaf runs inside that scrape worker.

After a parent/hub finishes its own work, if any descendant is still pending, running, or waiting, the parent becomes **waiting**. It becomes **done** only when every descendant has finished.

- If a **child fails**, the parent is still **done**, with **warnings** (not failed).
- **Cancelled** children are finished work; they do not fail the parent.
- If the **parent itself** fails (bad URL, fetch error, …), its status is **failed**.

## Errors you might see

| Situation | What to try |
|-----------|-------------|
| **Unsupported URL** / not an Arles album | The page is not a photo grid or album list this importer understands. Use a real Arles `index.html`, or [upload a folder](folder-import.md) instead. |
| **Could not download** (often with an HTTP status) | Check the URL. If the site needs a session, add a `Cookie` (or other) header and try again. |
| **No album photos or child galleries** | The page downloaded but had nothing to import. Confirm you opened the gallery index, not a random site page. |

Progress and errors show on the job page. Re-run from **Jobs** or **Reprocess** on the saved album.

## Reprocess a web album

**Reprocess** on a web preview **downloads again** from the original URL (HTML, high-res files, captions, journal), using the stored URL and headers. You confirm first. That replaces the stored preview and edits. It does **not** retry a hub as if it were a leaf, and it does not touch Google Photos.

Folder reprocess only re-reads files already on the server — see [Using the app](using-the-app.md#reprocess).

## Restart after cancel

If you **cancel** a hub (or other scrape) mid-way, **Restart** starts a **new** job. You can restart **all** child galleries, or only **remaining / failed** ones (already-**done** children are skipped, matched by URL). Details: [Using the app](using-the-app.md#restart-a-cancelled-run).

## Next

- [Using the app](using-the-app.md)
- [Folder import](folder-import.md)
- [Album layout](album-layout.md)
- [Google Photos access](google-photos.md)
