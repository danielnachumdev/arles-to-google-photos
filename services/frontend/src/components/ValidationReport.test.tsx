import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { ValidationReport } from '../api/types.ts'
import { setAppLanguage } from '../lib/i18n/store.ts'
import { ValidationReportView } from './ValidationReport.tsx'

const report: ValidationReport = {
  root_url: 'https://example.com/gallery/',
  identical: false,
  summary: {
    matched: 2,
    only_remote: 1,
    only_photos: 0,
    content_mismatches: 1,
  },
  warnings: ['Skipped decoy page'],
  matched: [
    {
      title_id: 'day1',
      title: 'Demo Day 1',
      remote_url: 'https://example.com/gallery/day1/',
      photos_album_id: 'ph-day1',
      photos_product_url: 'https://photos.google.com/lr/album/ph-day1',
      identical: false,
      only_remote_items: ['20120802_01'],
      only_photos_items: ['20120802_99'],
      mismatches: [
        {
          item_id: '20120802_02',
          field: 'caption',
          remote: 'Arles caption',
          photos: 'Photos caption',
        },
        {
          item_id: '20120802_03',
          field: 'size',
          remote: 2048,
          photos: 4096,
        },
      ],
    },
    {
      title_id: 'day2',
      title: 'Demo Day 2',
      remote_url: 'https://example.com/gallery/day2/',
      photos_album_id: 'ph-day2',
      photos_product_url: 'https://photos.google.com/lr/album/ph-day2',
      identical: true,
    },
  ],
  only_remote: [
    {
      title_id: 'orphan-remote',
      title: 'Orphan remote album',
      item_count: 4,
      url: 'https://example.com/gallery/orphan/',
    },
  ],
  only_photos: [],
}

describe('ValidationReportView', () => {
  beforeEach(() => {
    setAppLanguage('en', false)
  })

  afterEach(() => {
    setAppLanguage('he', false)
  })

  it('shows summary and defaults to the first album with differences', () => {
    render(<ValidationReportView report={report} />)

    expect(screen.getByRole('heading', { name: 'Validation report' })).toBeInTheDocument()
    expect(
      screen.getByText('Differences found between remote and Photos.'),
    ).toBeInTheDocument()
    expect(screen.getByText('2 matched by title')).toBeInTheDocument()
    expect(screen.getByText('1 only on remote')).toBeInTheDocument()

    const selected = screen.getByRole('button', { name: /Demo Day 1/i })
    expect(selected).toHaveAttribute('aria-current', 'true')

    expect(screen.getByText(/4 differences between remote and Photos/i)).toBeInTheDocument()
    expect(screen.getByText('20120802_01')).toBeInTheDocument()
    expect(screen.getByText('20120802_99')).toBeInTheDocument()
    expect(screen.getByText('Arles caption')).toBeInTheDocument()
    expect(screen.getByText('Photos caption')).toBeInTheDocument()
    expect(screen.getByText('2.0 KB')).toBeInTheDocument()
    expect(screen.getByText('4.0 KB')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open remote album' })).toHaveAttribute(
      'href',
      'https://example.com/gallery/day1/',
    )
    expect(screen.getByRole('link', { name: 'Open in Google Photos' })).toHaveAttribute(
      'href',
      'https://photos.google.com/lr/album/ph-day1',
    )
  })

  it('filters to issues and lets the user open another album', () => {
    render(<ValidationReportView report={report} />)

    fireEvent.click(screen.getByRole('tab', { name: 'With differences' }))
    expect(screen.getByRole('button', { name: /Demo Day 1/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Orphan remote album/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Demo Day 2/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Orphan remote album/i }))
    expect(
      screen.getByText(
        'This album exists on the remote gallery but not among app-created Photos albums.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open remote album' })).toHaveAttribute(
      'href',
      'https://example.com/gallery/orphan/',
    )
  })

  it('searches albums by title', () => {
    render(<ValidationReportView report={report} />)

    fireEvent.click(screen.getByRole('tab', { name: 'All' }))
    fireEvent.change(screen.getByPlaceholderText('Search by album title…'), {
      target: { value: 'Day 2' },
    })

    expect(screen.getByRole('button', { name: /Demo Day 2/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Demo Day 1/i })).not.toBeInTheDocument()
    expect(screen.getByText('Remote and Photos match for this album.')).toBeInTheDocument()
  })

  it('lists discovery warnings', () => {
    render(<ValidationReportView report={report} />)

    const details = screen.getByText('1 warning during discovery').closest('details')
    expect(details).toBeTruthy()
    fireEvent.click(within(details as HTMLElement).getByText('1 warning during discovery'))
    expect(screen.getByText('Skipped decoy page')).toBeInTheDocument()
  })
})
