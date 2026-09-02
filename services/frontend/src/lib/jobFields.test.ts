import { describe, expect, it } from 'vitest'
import type { Job, JobChild } from '../api/types.ts'
import { JobBuilder } from '../testing/index.ts'
import { t } from './language.ts'
import {
  childDisplayLabel,
  childHasAlbumDesk,
  inferImportOrigin,
  isHostnameLabel,
  isWebImportJob,
  jobDocumentLabel,
  jobErrorMessage,
  jobFolderLabel,
  jobGalleryTitle,
  jobPhotoCount,
  jobPhotosUrl,
  jobScrapeUrl,
  parseHttpStatus,
} from './jobFields.ts'

const PREVIEW_JOB: Job = JobBuilder.preview({
  id: 'preview-1',
  folder_label: 'Day1',
  preview: {
    title: 'קיץ 2012',
    description: null,
    multi_index: false,
    journal: null,
    items: [],
  },
}).build()

describe('isHostnameLabel', () => {
  it('detects website hosts and ignores real folder names', () => {
    expect(isHostnameLabel('albums.example')).toBe(true)
    expect(isHostnameLabel('photos.example')).toBe(true)
    expect(isHostnameLabel('Day1')).toBe(false)
    expect(isHostnameLabel('SkiTrip')).toBe(false)
    expect(isHostnameLabel(null)).toBe(false)
  })
})

describe('job field helpers', () => {
  it('infers import origin from explicit field or scrape signals', () => {
    expect(inferImportOrigin({ import_origin: 'folder' })).toBe('folder')
    expect(inferImportOrigin({ import_origin: 'web' })).toBe('web')
    expect(inferImportOrigin({ type: 'preview' })).toBe('folder')
    expect(inferImportOrigin({ type: 'preview', parent_job_id: 'scrape-1' })).toBe('web')
    expect(inferImportOrigin({ type: 'scrape' })).toBe('web')
    expect(inferImportOrigin({ type: 'preview', scrape_url: 'https://albums.example/day1' })).toBe(
      'web',
    )
  })

  it('detects web vs folder import origin', () => {
    expect(isWebImportJob({ import_origin: 'web' })).toBe(true)
    expect(isWebImportJob({ import_origin: 'folder', parent_job_id: 'scrape-1' })).toBe(false)
    expect(isWebImportJob({ type: 'scrape' })).toBe(true)
    expect(isWebImportJob({ parent_job_id: 'scrape-1' })).toBe(true)
    expect(isWebImportJob({ scrape_url: 'https://albums.example/day1' })).toBe(true)
    expect(isWebImportJob({ type: 'preview' })).toBe(false)
  })

  it('reads scrape URL from scrape_url or url', () => {
    expect(jobScrapeUrl({ scrape_url: 'https://albums.example/day1' })).toBe(
      'https://albums.example/day1',
    )
    expect(jobScrapeUrl({ url: 'https://gallery.example/' })).toBe('https://gallery.example/')
    expect(jobScrapeUrl({})).toBeNull()
  })

  it('uses gallery title and real folder names for preview jobs', () => {
    expect(jobGalleryTitle(PREVIEW_JOB)).toBe('קיץ 2012')
    expect(jobFolderLabel(PREVIEW_JOB)).toBe('Day1')
    expect(jobDocumentLabel(PREVIEW_JOB)).toBe('קיץ 2012')
  })

  it('does not treat scrape hostname as album or folder', () => {
    const scrape: Job = {
      id: 'scrape-1',
      status: 'running',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      folder_label: 'albums.example',
      scrape_url: 'https://albums.example/day1',
    }
    expect(jobGalleryTitle(scrape)).toBeNull()
    expect(jobGalleryTitle({ type: 'scrape', title: 'albums.example' })).toBeNull()
    expect(jobFolderLabel(scrape)).toBeNull()
    expect(jobDocumentLabel(scrape)).toBe('https://albums.example/day1')
    expect(jobFolderLabel({ type: 'preview', folder_label: 'albums.example' })).toBeNull()
  })

  it('labels scrape children with URL and preview children with gallery title', () => {
    const scrapeChild: JobChild = {
      id: 'scrape-child',
      type: 'scrape',
      title: 'albums.example',
      folder_label: 'albums.example',
      scrape_url: 'https://albums.example/day2',
    }
    const previewChild: JobChild = {
      id: 'preview-child',
      type: 'preview',
      title: 'Day 1',
      preview: {
        title: 'Day 1',
        description: null,
        multi_index: false,
        journal: null,
        items: [],
      },
    }
    const runningPreview: JobChild = {
      id: 'preview-early',
      type: 'preview',
      folder_label: 'albums.example',
      preview: null,
    }
    expect(childDisplayLabel(scrapeChild)).toBe('https://albums.example/day2')
    expect(childDisplayLabel(previewChild)).toBe('Day 1')
    expect(childDisplayLabel(runningPreview)).toBe('preview-early')
    expect(childHasAlbumDesk(previewChild)).toBe(true)
    expect(childHasAlbumDesk(runningPreview)).toBe(false)
    expect(childHasAlbumDesk(scrapeChild)).toBe(false)
  })

  it('returns photo count for preview and upload, never scrape', () => {
    expect(jobPhotoCount({ type: 'scrape', item_count: 9, preview: { items: [{}] } })).toBeNull()
    expect(jobPhotoCount({ type: 'preview', preview: { items: [{}, {}] } })).toBe(2)
    expect(jobPhotoCount({ type: 'preview', preview: { items: [] } })).toBe(0)
    expect(jobPhotoCount({ type: 'upload', item_count: 4 })).toBe(4)
    expect(jobPhotoCount({ type: 'preview', item_count: 0 })).toBeNull()
    expect(jobPhotoCount({ type: 'upload', preview: null, item_count: 0 })).toBeNull()
  })

  it('formats scrape error codes into clear copy with the URL', () => {
    const url = 'https://albums.example/album/index2012.html'
    expect(parseHttpStatus('Failed to download gallery: x (HTTP 404)')).toBe('404')
    expect(parseHttpStatus('nope')).toBeNull()
    expect(
      jobErrorMessage({
        type: 'scrape',
        error_code: 'not_arles',
        error: 'Not a supported Arles album: ' + url,
        scrape_url: url,
      }),
    ).toBe(t.errorScrapeUnsupported(url))
    expect(
      jobErrorMessage({
        type: 'scrape',
        error_code: 'fetch_failed',
        error: `Failed to download gallery: ${url} (HTTP 401)`,
        scrape_url: url,
      }),
    ).toBe(t.errorScrapeFetch(url, '401'))
    expect(
      jobErrorMessage({
        type: 'scrape',
        error_code: 'scrape_empty',
        scrape_url: url,
      }),
    ).toBe(t.errorScrapeEmpty(url))
    expect(
      jobErrorMessage({
        type: 'preview',
        error: 'interrupted',
        error_code: 'interrupted',
      }),
    ).toBe(t.errorInterrupted)
    expect(jobErrorMessage({ type: 'upload', error: 'interrupted' })).toBe(t.errorInterrupted)
    expect(
      jobErrorMessage({
        type: 'scrape',
        error: 'site down',
      }),
    ).toBe(t.errorScrape('site down'))
    expect(jobErrorMessage({ type: 'preview', error: 'parse failed' })).toBe('parse failed')
  })

  it('returns Photos URL for preview and upload when set, never scrape', () => {
    expect(jobPhotosUrl({ type: 'scrape', product_url: 'https://photos.example/x' })).toBeNull()
    expect(jobPhotosUrl({ type: 'upload', product_url: 'https://photos.example/x' })).toBe(
      'https://photos.example/x',
    )
    expect(jobPhotosUrl({ type: 'preview', product_url: 'https://photos.example/y' })).toBe(
      'https://photos.example/y',
    )
    expect(jobPhotosUrl({ type: 'preview', product_url: null })).toBeNull()
    expect(jobPhotosUrl({ type: 'upload', product_url: '  ' })).toBeNull()
  })
})
