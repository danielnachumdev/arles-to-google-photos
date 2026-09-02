import { describe, expect, it } from 'vitest'
import type { AlbumPreview } from '../api/types.ts'
import {
  computePreviewDirty,
  isPreviewDirty,
  normalizeJournalHeading,
  normalizeJournalParagraphs,
  previewDirtyFields,
} from './previewDirty.ts'

const PREVIEW: AlbumPreview = {
  title: 'קיץ 2012',
  description: 'תיאור גלריה',
  multi_index: false,
  journal: { heading: 'יומן קיץ', paragraphs: ['פסקה אחת', 'פסקה שתיים'] },
  items: [
    {
      id: '20120802_01',
      relpath: 'hrimages/20120802_01hr.JPG',
      caption: 'יום ראשון',
      size_bytes: 12,
      last_modified: '2012-08-02T10:00:00',
      taken_on: '2012-08-02',
    },
    {
      id: '20120802_02',
      relpath: 'hrimages/20120802_02hr.JPG',
      caption: 'יום שני',
      size_bytes: 8,
      last_modified: '2012-08-02T11:00:00',
      taken_on: '2012-08-02',
    },
  ],
}

const CLEAN_VALUES = {
  title: 'קיץ 2012',
  description: 'תיאור גלריה',
  journalHeading: 'יומן קיץ',
  journalBody: 'פסקה אחת\n\nפסקה שתיים',
  captions: {
    '20120802_01': 'יום ראשון',
    '20120802_02': 'יום שני',
  },
}

describe('normalizeJournalParagraphs', () => {
  it('splits on blank lines, trims, and drops empties', () => {
    expect(normalizeJournalParagraphs('  a  \n\n\n  b\n  \n\nc  ')).toEqual(['a', 'b', 'c'])
  })
})

describe('normalizeJournalHeading', () => {
  it('trims and treats blank as null', () => {
    expect(normalizeJournalHeading('  יומן  ')).toBe('יומן')
    expect(normalizeJournalHeading('   ')).toBeNull()
    expect(normalizeJournalHeading('')).toBeNull()
  })
})

describe('previewDirtyFields', () => {
  it('is clean against the last applied preview snapshot', () => {
    const fields = previewDirtyFields(PREVIEW, CLEAN_VALUES)
    expect(fields).toEqual({
      title: false,
      description: false,
      journalHeading: false,
      journalBody: false,
      captions: {
        '20120802_01': false,
        '20120802_02': false,
      },
    })
    expect(isPreviewDirty(fields)).toBe(false)
    expect(computePreviewDirty(PREVIEW, CLEAN_VALUES).dirty).toBe(false)
  })

  it('treats extra journal blank lines and heading whitespace as clean', () => {
    const fields = previewDirtyFields(PREVIEW, {
      ...CLEAN_VALUES,
      journalHeading: '  יומן קיץ  ',
      journalBody: 'פסקה אחת\n\n\nפסקה שתיים\n',
    })
    expect(fields.journalHeading).toBe(false)
    expect(fields.journalBody).toBe(false)
    expect(isPreviewDirty(fields)).toBe(false)
  })

  it('treats a null journal and empty heading/body as clean', () => {
    const preview: AlbumPreview = { ...PREVIEW, journal: null }
    const fields = previewDirtyFields(preview, {
      ...CLEAN_VALUES,
      journalHeading: '',
      journalBody: '',
    })
    expect(fields.journalHeading).toBe(false)
    expect(fields.journalBody).toBe(false)
    expect(isPreviewDirty(fields)).toBe(false)
  })

  it('treats a null gallery description and empty field as clean', () => {
    const preview: AlbumPreview = { ...PREVIEW, description: null }
    const fields = previewDirtyFields(preview, { ...CLEAN_VALUES, description: '' })
    expect(fields.description).toBe(false)
    expect(isPreviewDirty(fields)).toBe(false)
  })

  it('flags a changed title', () => {
    const fields = previewDirtyFields(PREVIEW, { ...CLEAN_VALUES, title: 'חורף' })
    expect(fields.title).toBe(true)
    expect(fields.description).toBe(false)
    expect(isPreviewDirty(fields)).toBe(true)
  })

  it('flags changed journal paragraphs', () => {
    const fields = previewDirtyFields(PREVIEW, {
      ...CLEAN_VALUES,
      journalBody: 'פסקה אחת\n\nפסקה אחרת',
    })
    expect(fields.journalBody).toBe(true)
    expect(fields.journalHeading).toBe(false)
    expect(isPreviewDirty(fields)).toBe(true)
  })

  it('flags a changed journal heading', () => {
    const fields = previewDirtyFields(PREVIEW, {
      ...CLEAN_VALUES,
      journalHeading: 'כותרת חדשה',
    })
    expect(fields.journalHeading).toBe(true)
    expect(isPreviewDirty(fields)).toBe(true)
  })

  it('flags a single changed caption', () => {
    const fields = previewDirtyFields(PREVIEW, {
      ...CLEAN_VALUES,
      captions: { ...CLEAN_VALUES.captions, '20120802_02': 'עודכן' },
    })
    expect(fields.captions['20120802_01']).toBe(false)
    expect(fields.captions['20120802_02']).toBe(true)
    expect(fields.title).toBe(false)
    expect(isPreviewDirty(fields)).toBe(true)
  })

  it('is clean when preview is missing', () => {
    expect(computePreviewDirty(null, CLEAN_VALUES).dirty).toBe(false)
    expect(computePreviewDirty(undefined, CLEAN_VALUES).dirty).toBe(false)
  })
})
