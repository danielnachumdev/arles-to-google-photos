# Folder import (local Arles export)

Secondary path: if you already have an Arles HTML album on disk, upload that folder instead of a gallery URL.

**Web import** (paste a URL) is the default on **New**. Details: [Web import](web-import.md).

## How to import in the UI

1. On **New**, the desk opens on **Import from web**. Switch to **Or upload an exported album folder**.
2. Click the folder picker and choose the album directory — the folder that contains `index.html`, not a parent of several albums.
3. Confirm the UI lists the required pieces (`index.html`, `hrimages/`, `imagepages/`) or shows a file count after you pick.
4. Optionally check **Auto-publish to Photos** (Google sign-in up front; publish begins when preview is ready).
5. Click **Prepare preview**.

Large folders are fine. Progress streams while files are uploaded and parsed. When preview is ready, you land on the album desk.

Docker does **not** mount `./data` (or any host album folder) as a source. You always pick the folder in the browser; files are uploaded to the server. See [Getting started](getting-started.md).

## Required tree

```
ALBUM_FOLDER/
├── index.html               # required — title, optional description, journal, thumbnail grid
├── index1.html, …           # optional extra index pages (“multi-index”)
├── hrimages/                # required — high-res photos / videos
│   └── 20120802_01hr.JPG
└── imagepages/
    └── 20120802_01.html     # per-item page; `.imagetitle` → Photos title
```

Optional Arles extras (`thumbnails/`, `index.css`, `Gallery.arl`, …) are fine. They are not a substitute for `index.html` + `hrimages/` + `imagepages/`. If a required piece is missing, preview fails.

Deeper layout notes (dates, EXIF, video transcode): [Album layout](album-layout.md).

## Filename mapping (trailing `hr`)

High-res stems often end with `hr` (any case): `20120802_01hr.JPG` → item id `20120802_01` → `imagepages/20120802_01.html`.

Only a **trailing** `hr` is stripped. A leading `hr` in the name is left alone. Do not globally delete the letters `hr` from the filename.

Videos use the same rule: `clip01hr.wmv` → id `clip01` → `imagepages/clip01.html`.

## Who is in the gallery, and in what order

Membership and order come from the **thumbnail grid** on `index.html`: links that look like `imagepages/ID.html`, in page order.

That is **not** a filesystem sort of `hrimages/`. Decoy files such as `Text.jpg` or `aaa.jpg` are skipped if they are not linked from the grid.

## Title, description, journal

| Field | Where it comes from | Notes |
|-------|---------------------|--------|
| Gallery title | `.gallerytitle` on `index.html` | Required for a normal Arles index |
| Gallery description | `.gallerydesc` | Often empty. **Skipped** when the album is multi-index |
| Image / video title | `.imagetitle` on the per-item HTML page | Editable in the preview |
| Journal | Word HTML `div.WordSection1` at the bottom of `index.html` | Heading + paragraphs; editable. Empty journal is omitted on publish |

Journal and gallery description are different. On publish, Google Photos text blocks are ordered so the album reads **heading → journal body → gallery description → photos**.

## Multi-index

If the folder has several `index*.html` files (`index.html`, `index1.html`, …), the album is **multi-index**. Gallery description is not used.

## Video (including WMV)

Arles albums can include video in `hrimages/` (`.wmv`, `.mp4`, `.mov`, `.avi`, and similar). Per-item HTML may **embed** the video instead of only showing a still.

For preview in the browser, the app may extract a poster frame and transcode non-browser formats (for example WMV) to a local `.mp4`. If transcode fails, preview still finishes; publish still uploads the original media. More detail: [Album layout](album-layout.md#video-including-wmv).

## Reprocess

**Reprocess** on a folder preview re-parses the album files **already stored** on the server (same id). It does not re-read your original disk folder. Web reprocess re-downloads from the URL instead — see [Using the app](using-the-app.md#reprocess).

## Next

- [Web import](web-import.md) — default path (gallery URL)
- [Album layout](album-layout.md) — dates, EXIF, video transcode
- [Using the app](using-the-app.md) — preview, edit, publish
- [Getting started](getting-started.md)
