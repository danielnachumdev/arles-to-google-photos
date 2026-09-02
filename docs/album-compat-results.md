# Album compat results

Inventory + leaf/nav support after the Aug 2026 compat work. No secrets or live hostnames below.

## What shipped

| Layer | Change |
|-------|--------|
| Year / archive hubs | Child album links may be **1–2** path segments (`year/album/index.html`) → scrape returns child URLs |
| Trip parents | Nested day folders still enqueue as children |
| Flat `*hr` / `*tn` | Root-level media (no `hrimages/`) parse + scrape into a normal tree |
| Windows-1255 HTML | Parser/detect decode without UTF-8 failure |
| Missing image page | Scrape skips 404 `imagepages/` and keeps OK photos |
| Flash stub | Still rejected (not a photo album) |
| Loose-media folder fallback | Folder ingest may import by filename when the index grid is incomplete; UI warns via `structure_fallback` |
| Nested / path-agnostic media | Detect + parse + scrape follow media at any relative depth (skip `icons/` / `thumbnails/`) |
| Single-image viewer index | Digital Dutch `image.css` + content `<img src>` (no media/`imagepages` grid); caption from index `imagetitle` |
| Trailing-`hr` imagepages | `imagepages/{id}hr.html` normalizes to the same id as `hrimages/{id}hr.*` |

Fixtures/tests use generic titles and `albums.example` only.

## Local parse (hydrated dump)

Source: `data/onedrive_8-12-2026` → `data/folder_parse_scan.json`

| Metric | Value |
|--------|------:|
| Albums with `index.html` | 186 |
| Parse OK | **185** |
| Fail | **1** (Flash / non-photo stub) |

## Local parse (full OneDrive tree)

Source: local OneDrive album tree → `data/onedrive_parse_scan.json`  
Latest full reparse after viewer + trailing-`hr` imagepage fixes.

| Metric | Value |
|--------|------:|
| Albums with `index.html` | 853 |
| Parse OK (items &gt; 0) | **687** |
| Of which proper (no fallback) | **673** |
| Of which `structure_fallback` | **14** |
| Fail | **166** |

### Failures (not new leaf formats)

| Count | Cause | Meaning |
|------:|-------|---------|
| 157 | No media / empty index | Almost all are **meta-refresh** stubs (Google Photos redirects): `index.html` only |
| 8 | Hub / parent | Stub index; real albums live in child folders |
| 1 | Flash stub | Non-photo showcase |

## Remote vs local catalog

Source: live album crawl → `data/full_album_index.json` (same-day rescan)

| Metric | Value |
|--------|------:|
| Remote leaf URLs crawled | 816 |
| Remote nav pages | 41 |
| Remote: standard `imagepages` leaf | **536** |
| Remote: direct / nested media leaf | **118** |
| Remote: unknown / non-Arles | **162** |
| Remote: Arles leaf, 0 items | **0** |
| In both remote + local | **816** |
| Remote only | **0** |
| Local-only extras | 37 (hubs / day-trip parents / false nested indexes) |

## Rescan after trailing-`hr` imagepage fix

Baseline = previous `onedrive_parse_scan.json` / `full_album_index.json` (already included loose-media + nested-path work; **before** this full reparse captured the viewer + `*hr.html` id fix).  
Diff: `data/rescan_diff_report.json` · summary: `data/_improvement_summary.json`

| Check | Result |
|-------|--------|
| Remote leaf set | **Identical** (816; +0 / −0) |
| Local album set | **Identical** (853; +0 / −0) |
| Local OK / fail counts | **Unchanged** (687 / 166) — **no ok↔fail regressions** |
| Proper vs fallback | `ok` **661 → 673**; `ok_structure_fallback` **26 → 14** (**12** albums upgraded off fallback) |
| Remote Arles 0-item leaves | **1 → 0** (`2005/0905_2`: viewer → 1 item, `leaf_direct_media_grid`) |
| Direct-media remote leaves | **117 → 118** |

### Fallback → proper (12)

Includes single-image viewers (real captions/titles) and **`2018/0218_1`** (trailing-`hr` imagepages): gallery membership **95 → 43** (loose had pulled in `More/` / `No/`; proper parse keeps the 43 index-linked photos only).

### Spotlight

| Album | Before | After |
|-------|--------|-------|
| `2005/0905_2` | Local fallback; remote `leaf_arles_no_items` (0) | Proper local parse; remote **1** item |
| `2018/0218_1` | Local fallback (95 items) | Proper parse (**43** items + captions); remote already OK |

### Remaining work (not regressions)

Hard fails are still stubs/hubs/Flash. Remaining **14** `structure_fallback` albums are mostly hubs with empty parent indexes that still happen to discover nested media, or non-Arles folders with files only.

## Takeaway

Supported leaf shapes (standard, flat hr/tn, Win-1255, nested media, single-image viewer, trailing-`hr` imagepages) parse cleanly. Remaining misses are hubs, Flash, and Google Photos redirect stubs — not another undocumented photo-leaf layout.

## Artifacts

| File | Contents |
|------|----------|
| `data/album_compat_browser.html` | Interactive table (regenerate: `python data/build_album_compat_browser.py`) |
| `data/folder_parse_scan.json` | Hydrated dump parse |
| `data/onedrive_parse_scan.json` | Full OneDrive parse |
| `data/full_album_index.json` | Remote crawl + overlap |
| `data/rescan_diff_report.json` | Latest vs previous snapshot |
| `data/_improvement_summary.json` | Fallback upgrades + remote bucket deltas |
| `tests/export/test_album_compat_failures.py` | Compat TDD matrix |
