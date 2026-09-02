import { describe, expect, it } from 'vitest'
import { t } from './language.ts'
import {
  previewDescriptionLabel,
  previewItemKind,
  previewOpenAria,
} from './previewMedia.ts'

describe('previewItemKind', () => {
  it('uses an explicit kind when present', () => {
    expect(previewItemKind({ relpath: 'hrimages/a.wmv', kind: 'image' })).toBe('image')
    expect(previewItemKind({ relpath: 'hrimages/a.jpg', kind: 'photo' })).toBe('image')
    expect(previewItemKind({ relpath: 'hrimages/a.jpg', kind: 'video' })).toBe('video')
  })

  it('infers video from relpath when kind is missing', () => {
    expect(previewItemKind({ relpath: 'hrimages/0512_1_06[1]hr.wmv' })).toBe('video')
    expect(previewItemKind({ relpath: 'hrimages/clip01hr.MP4', kind: null })).toBe('video')
    expect(previewItemKind({ relpath: 'hrimages/clip.MOV' })).toBe('video')
    expect(previewItemKind({ relpath: 'hrimages/clip.avi' })).toBe('video')
    expect(previewItemKind({ relpath: 'hrimages/20120802_01hr.JPG' })).toBe('image')
    expect(previewItemKind({})).toBe('image')
  })
})

describe('preview labels', () => {
  it('uses photo copy for JPEG items', () => {
    const item = { id: '20120802_01', relpath: 'hrimages/20120802_01hr.JPG' }
    expect(previewDescriptionLabel(item, t)).toBe(t.descriptionLabel)
    expect(previewOpenAria(item, t)).toBe(t.openPreviewAria(item.id))
  })

  it('uses video copy for WMV items', () => {
    const item = { id: 'clip01', relpath: 'hrimages/clip01hr.wmv' }
    expect(previewDescriptionLabel(item, t)).toBe(t.videoDescriptionLabel)
    expect(previewOpenAria(item, t)).toBe(t.openVideoPreviewAria(item.id))
  })
})
