import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { t } from '../lib/language.ts'
import { PreviewItemBuilder } from '../testing/index.ts'
import { ImagePreviewModal, type ImagePreviewTarget } from './ImagePreviewModal.tsx'

const TARGET: ImagePreviewTarget = {
  id: '20120802_01',
  index: 3,
  src: '/api/jobs/job-1/media/20120802_01',
}

describe('ImagePreviewModal', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<ImagePreviewModal target={null} onClose={() => undefined} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the full image with photo id, index, and aria-modal', () => {
    render(<ImagePreviewModal target={TARGET} onClose={() => undefined} />)
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleName(/20120802_01/)
    expect(screen.getByText('#3')).toBeInTheDocument()
    const image = screen.getByRole('img', { name: '20120802_01' })
    expect(image).toHaveAttribute('src', TARGET.src)
    // Portal to body so ancestor transforms (e.g. .app rise) cannot trap fixed layout.
    expect(dialog.parentElement).toBe(document.body)
  })

  it('closes from the close control, backdrop, and Escape', () => {
    const onClose = vi.fn()
    render(<ImagePreviewModal target={TARGET} onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: t.close }))
    expect(onClose).toHaveBeenCalledTimes(1)

    const stage = document.querySelector('.image-preview-modal__stage')
    expect(stage).toBeTruthy()
    fireEvent.click(stage!)
    expect(onClose).toHaveBeenCalledTimes(2)

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(3)
  })

  it('does not close when the photo itself is clicked', () => {
    const onClose = vi.fn()
    render(<ImagePreviewModal target={TARGET} onClose={onClose} />)
    fireEvent.click(screen.getByRole('img', { name: '20120802_01' }))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('locks body scroll while open and restores it when closed', () => {
    document.body.style.overflow = 'auto'
    const { rerender } = render(<ImagePreviewModal target={TARGET} onClose={() => undefined} />)
    expect(document.body.style.overflow).toBe('hidden')
    rerender(<ImagePreviewModal target={null} onClose={() => undefined} />)
    expect(document.body.style.overflow).toBe('auto')
    document.body.style.overflow = ''
  })

  it('shows an image title footer when the photo has a caption', () => {
    const caption = 'יום ראשון בחוף'
    render(
      <ImagePreviewModal
        target={{ ...TARGET, caption }}
        onClose={() => undefined}
      />,
    )
    const dialog = screen.getByRole('dialog')
    const footer = screen.getByText(caption).closest('.image-preview-modal__footer')
    expect(footer).toBeTruthy()
    expect(screen.getByText(t.descriptionLabel)).toBeInTheDocument()
    expect(dialog).toHaveAttribute('aria-describedby', footer!.id)
    expect(screen.getByRole('img', { name: caption })).toBeInTheDocument()
  })

  it('hides the footer when the caption is empty or whitespace', () => {
    const { rerender } = render(
      <ImagePreviewModal target={{ ...TARGET, caption: '' }} onClose={() => undefined} />,
    )
    expect(screen.queryByText(t.descriptionLabel)).not.toBeInTheDocument()
    expect(screen.getByRole('dialog')).not.toHaveAttribute('aria-describedby')

    rerender(
      <ImagePreviewModal target={{ ...TARGET, caption: '   \n\t' }} onClose={() => undefined} />,
    )
    expect(screen.queryByText(t.descriptionLabel)).not.toBeInTheDocument()

    rerender(
      <ImagePreviewModal target={{ ...TARGET, caption: null }} onClose={() => undefined} />,
    )
    expect(screen.queryByText(t.descriptionLabel)).not.toBeInTheDocument()
  })

  it('does not close when the image title footer is clicked', () => {
    const onClose = vi.fn()
    render(
      <ImagePreviewModal
        target={{ ...TARGET, caption: 'כיתוב' }}
        onClose={onClose}
      />,
    )
    fireEvent.click(screen.getByText('כיתוב'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('uses video title kicker for video kind or relpath', () => {
    const caption = 'קליפ מהטיול'
    const { rerender } = render(
      <ImagePreviewModal
        target={{ ...TARGET, caption, relpath: 'hrimages/clip01hr.wmv' }}
        onClose={() => undefined}
      />,
    )
    expect(screen.getByText(t.videoDescriptionLabel)).toBeInTheDocument()
    expect(screen.queryByText(t.descriptionLabel)).not.toBeInTheDocument()

    rerender(
      <ImagePreviewModal
        target={{ ...TARGET, caption, kind: 'video', relpath: 'hrimages/clip01hr.JPG' }}
        onClose={() => undefined}
      />,
    )
    expect(screen.getByText(t.videoDescriptionLabel)).toBeInTheDocument()
    expect(screen.queryByText(t.descriptionLabel)).not.toBeInTheDocument()
  })

  it('renders a native video player for video targets', () => {
    const playSrc = '/api/jobs/job-1/media/clip01?variant=play'
    const poster = '/api/jobs/job-1/media/clip01?variant=thumb'
    render(
      <ImagePreviewModal
        target={{
          id: 'clip01',
          index: 2,
          src: playSrc,
          kind: 'video',
          relpath: 'hrimages/clip01hr.wmv',
          poster,
        }}
        onClose={() => undefined}
      />,
    )

    const video = document.querySelector('video')
    expect(video).toBeTruthy()
    expect(video).toHaveAttribute('controls')
    expect(video).toHaveAttribute('src', playSrc)
    expect(video).toHaveAttribute('poster', poster)
    expect(video).toHaveAttribute('aria-label', t.videoPreviewAria('clip01'))
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('keeps photos on an img, not a video player', () => {
    render(<ImagePreviewModal target={TARGET} onClose={() => undefined} />)
    expect(document.querySelector('video')).toBeNull()
    expect(screen.getByRole('img', { name: '20120802_01' })).toHaveAttribute('src', TARGET.src)
  })

  it('shows unavailable copy when the video element errors', () => {
    const video = PreviewItemBuilder.video().build()
    render(
      <ImagePreviewModal
        target={{
          id: video.id,
          index: 1,
          src: '/api/jobs/job-1/media/clip01?variant=play',
          kind: 'video',
          relpath: video.relpath,
        }}
        onClose={() => undefined}
      />,
    )
    const player = document.querySelector('video')
    expect(player).toBeTruthy()
    fireEvent.error(player!)
    expect(screen.getByRole('status')).toHaveTextContent(t.videoPreviewUnavailable)
  })
})
