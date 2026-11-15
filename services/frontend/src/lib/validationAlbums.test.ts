import { describe, expect, it } from 'vitest'
import type { ValidationReport } from '../api/types.ts'
import {
  buildValidationAlbumEntries,
  defaultValidationAlbumKey,
  filterValidationAlbums,
  formatValidationValue,
  isRemoteSmallerSizeMismatch,
  matchedIssueCount,
  withValidationViewOptions,
} from './validationAlbums.ts'

const sampleReport: ValidationReport = {
  root_url: 'https://example.com/gallery/',
  identical: false,
  summary: {
    matched: 2,
    only_remote: 1,
    only_photos: 1,
    content_mismatches: 1,
  },
  matched: [
    {
      title_id: 'day1',
      title: 'Day 1',
      remote_url: 'https://example.com/gallery/day1/',
      photos_album_id: 'ph-day1',
      photos_product_url: 'https://photos.google.com/lr/album/ph-day1',
      identical: false,
      only_remote_items: ['20120802_01'],
      only_photos_items: [],
      mismatches: [
        {
          item_id: '20120802_02',
          field: 'caption',
          remote: 'Remote caption',
          photos: 'Photos caption',
        },
      ],
    },
    {
      title_id: 'day2',
      title: 'Day 2',
      remote_url: 'https://example.com/gallery/day2/',
      photos_album_id: 'ph-day2',
      photos_product_url: 'https://photos.google.com/lr/album/ph-day2',
      identical: true,
    },
  ],
  only_remote: [
    {
      title_id: 'extra-remote',
      title: 'Extra remote',
      item_count: 3,
      url: 'https://example.com/gallery/extra/',
    },
  ],
  only_photos: [
    {
      title_id: 'extra-photos',
      title: 'Extra photos',
      item_count: 2,
      product_url: 'https://photos.google.com/lr/album/ph-extra',
    },
  ],
}

describe('validationAlbums', () => {
  it('counts matched album issues', () => {
    expect(matchedIssueCount(sampleReport.matched![0]!)).toBe(2)
    expect(matchedIssueCount(sampleReport.matched![1]!)).toBe(0)
  })

  it('builds list entries with issue flags', () => {
    const entries = buildValidationAlbumEntries(sampleReport)
    expect(entries.map((entry) => entry.key)).toEqual([
      'matched:day1',
      'matched:day2',
      'only_remote:extra-remote',
      'only_photos:extra-photos',
    ])
    expect(entries[0]?.hasIssues).toBe(true)
    expect(entries[0]?.issueCount).toBe(2)
    expect(entries[1]?.hasIssues).toBe(false)
    expect(entries[2]?.kind).toBe('only_remote')
    expect(entries[3]?.kind).toBe('only_photos')
  })

  it('filters by issues, kind, and search query', () => {
    const entries = buildValidationAlbumEntries(sampleReport)
    expect(filterValidationAlbums(entries, 'issues', '').map((e) => e.key)).toEqual([
      'matched:day1',
      'only_remote:extra-remote',
      'only_photos:extra-photos',
    ])
    expect(filterValidationAlbums(entries, 'matched', '').map((e) => e.key)).toEqual([
      'matched:day1',
      'matched:day2',
    ])
    expect(filterValidationAlbums(entries, 'all', 'extra').map((e) => e.key)).toEqual([
      'only_remote:extra-remote',
      'only_photos:extra-photos',
    ])
  })

  it('defaults to the first album with differences', () => {
    const entries = buildValidationAlbumEntries(sampleReport)
    expect(defaultValidationAlbumKey(entries)).toBe('matched:day1')
    expect(defaultValidationAlbumKey(filterValidationAlbums(entries, 'matched', 'day 2'))).toBe(
      'matched:day2',
    )
    expect(defaultValidationAlbumKey([])).toBeNull()
  })

  it('formats empty and byte-size values for the mismatch table', () => {
    expect(formatValidationValue(null)).toBe('—')
    expect(formatValidationValue('')).toBe('—')
    expect(formatValidationValue('hello')).toBe('hello')
    expect(formatValidationValue(512)).toBe('512 B')
    expect(formatValidationValue(2048)).toBe('2.0 KB')
    expect(formatValidationValue('1048576')).toBe('1.0 MB')
  })

  it('detects remote-smaller size mismatches only', () => {
    expect(
      isRemoteSmallerSizeMismatch({
        item_id: 'a',
        field: 'size',
        remote: 100,
        photos: 200,
      }),
    ).toBe(true)
    expect(
      isRemoteSmallerSizeMismatch({
        item_id: 'a',
        field: 'size',
        remote: 300,
        photos: 200,
      }),
    ).toBe(false)
    expect(
      isRemoteSmallerSizeMismatch({
        item_id: 'a',
        field: 'caption',
        remote: 'x',
        photos: 'y',
      }),
    ).toBe(false)
  })

  it('suppresses remote-smaller size diffs and recomputes identical', () => {
    const sizedOnly: ValidationReport = {
      root_url: 'https://example.com/',
      identical: false,
      summary: {
        matched: 1,
        only_remote: 0,
        only_photos: 0,
        content_mismatches: 1,
      },
      matched: [
        {
          title_id: 'day1',
          title: 'Day 1',
          remote_url: 'https://example.com/day1/',
          photos_album_id: 'ph',
          photos_product_url: 'https://photos.google.com/lr/album/ph',
          identical: false,
          mismatches: [
            {
              item_id: '20120802_01',
              field: 'size',
              remote: 2048,
              photos: 4096,
            },
            {
              item_id: '20120802_02',
              field: 'size',
              remote: 9000,
              photos: 1000,
            },
            {
              item_id: '20120802_03',
              field: 'caption',
              remote: 'a',
              photos: 'b',
            },
          ],
        },
      ],
    }

    const viewed = withValidationViewOptions(sizedOnly, {
      suppressRemoteSmallerSizes: true,
    })
    expect(viewed.matched?.[0]?.mismatches).toEqual([
      {
        item_id: '20120802_02',
        field: 'size',
        remote: 9000,
        photos: 1000,
      },
      {
        item_id: '20120802_03',
        field: 'caption',
        remote: 'a',
        photos: 'b',
      },
    ])
    expect(viewed.matched?.[0]?.identical).toBe(false)
    expect(viewed.summary.content_mismatches).toBe(1)
    expect(viewed.identical).toBe(false)

    const onlySmaller: ValidationReport = {
      ...sizedOnly,
      matched: [
        {
          ...sizedOnly.matched![0]!,
          mismatches: [
            {
              item_id: '20120802_01',
              field: 'size',
              remote: 2048,
              photos: 4096,
            },
          ],
        },
      ],
    }
    const cleared = withValidationViewOptions(onlySmaller, {
      suppressRemoteSmallerSizes: true,
    })
    expect(cleared.identical).toBe(true)
    expect(cleared.matched?.[0]?.identical).toBe(true)
    expect(cleared.matched?.[0]?.mismatches).toEqual([])
    expect(cleared.summary.content_mismatches).toBe(0)
    expect(buildValidationAlbumEntries(cleared)[0]?.hasIssues).toBe(false)
  })
})
