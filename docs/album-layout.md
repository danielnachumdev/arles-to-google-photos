# Album layout (Arles export)

The importer expects an **Arles HTML album export**, the offline gallery [Arles Image Web Page Creator](https://www.digitaldutch.com/arles/) writes to disk.

If a required piece is missing, preview fails. Extra files that are not on the thumbnail grid are ignored.

## Importing this folder

Web import is the default in the app. To upload a folder from disk instead: on **New**, switch to **Or upload an exported album folder**, pick the album directory, then **Prepare preview**. Compose does **not** mount `./data` as a source — you pick the folder in the browser.

Full UI steps: [Folder import](folder-import.md).

## Folder tree

```
ALBUM_FOLDER/
├── index.html               # required — title, optional description, journal, thumbnail grid
├── index1.html, …           # optional extra index pages (“multi-index”)
├── hrimages/                # required — high-res photos / videos
│   └── 20120802_01hr.JPG
└── imagepages/
    └── 20120802_01.html     # per-item page; `.imagetitle` → Photos title
```

Optional Arles extras (`thumbnails/`, `index.css`, `Gallery.arl`, …) are fine. They are not a substitute for `index.html` + `hrimages/` + `imagepages/`.

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

## Dates

Each item’s **trip date** (`taken_on`) is parsed from an 8-digit `YYYYMMDD` prefix on the **item id** (for example `20120802_01` → 2 Aug 2012). It is not taken from camera EXIF or from “date modified”.

`last_modified` is the file’s filesystem time (or the browser `File.lastModified` on folder upload). The UI may warn when trip date and modified time disagree; that warning is **folder imports only**.

Before upload, capture time is written onto JPEGs (EXIF `DateTimeOriginal` / Digitised / DateTime) and file atime/mtime so Google Photos displays the trip date. Existing camera EXIF is kept if it already increases in gallery order; otherwise it is bumped by one second. Items with no EXIF use `taken_on` at midnight plus a few seconds for order.

## Video (including WMV)

Arles albums can include video in `hrimages/` (`.wmv`, `.mp4`, `.mov`, `.avi`, and similar). Per-item HTML may **embed** the video (`embed` / `object` / `source`, or a FileName parameter) instead of only showing a still.

On **web import**, the scraper downloads the video file when it can, plus a still **poster** (never the video itself as the poster).

For **preview in the browser**, the app tries to:

- extract a poster frame → `thumbnails/TN_{id}.jpg` (if no still already exists)
- transcode non-browser formats (for example WMV) → `preview/{id}.mp4`

If transcode fails, preview still finishes; the UI shows a video player when possible, or “This video cannot be played in the browser yet.” Publish still uploads the original media.

Click a video in the preview grid to open the player (controls + poster). Titles for videos use the same `.imagetitle` field (labeled “Video title” in the UI).

## Next

- [Folder import](folder-import.md)
- [Using the app](using-the-app.md)
- [Web import](web-import.md)
- [Getting started](getting-started.md)
