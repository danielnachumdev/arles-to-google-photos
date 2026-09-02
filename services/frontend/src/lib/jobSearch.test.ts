import type { JobSummary } from '../api/types.ts'
import { JobSummaryBuilder } from '../testing/index.ts'
import { filterJobs, matchesJobSearch } from './jobSearch.ts'

const SUMMER: JobSummary = JobSummaryBuilder.summer({ number: 42 }).build()
const WINTER: JobSummary = JobSummaryBuilder.winter({ number: 77 }).build()
const SCRAPE: JobSummary = JobSummaryBuilder.scrapeHost({
  id: 'job-scrape',
  status: 'running',
  scrape_url: 'https://gallery.example/day1',
}).build()

describe('filterJobs', () => {
  it('returns all jobs when the query is empty or whitespace', () => {
    expect(filterJobs([SUMMER, WINTER], '')).toEqual([SUMMER, WINTER])
    expect(filterJobs([SUMMER, WINTER], '   ')).toEqual([SUMMER, WINTER])
  })

  it('matches title, folder label, id, type, and status independently', () => {
    expect(filterJobs([SUMMER, WINTER], 'קיץ')).toEqual([SUMMER])
    expect(filterJobs([SUMMER, WINTER], 'skitrip')).toEqual([WINTER])
    expect(filterJobs([SUMMER, WINTER], 'JOB-SUMMER')).toEqual([SUMMER])
    expect(filterJobs([SUMMER, WINTER], '42')).toEqual([SUMMER])
    expect(filterJobs([SUMMER, WINTER], '77')).toEqual([WINTER])
    expect(filterJobs([SUMMER, WINTER], 'preview')).toEqual([WINTER])
    expect(filterJobs([SUMMER, WINTER], 'upload')).toEqual([SUMMER])
    expect(filterJobs([SUMMER, WINTER, SCRAPE], 'scrape')).toEqual([SCRAPE])
    expect(filterJobs([SUMMER, WINTER, SCRAPE], 'gallery.example')).toEqual([SCRAPE])
    expect(filterJobs([SUMMER, WINTER, SCRAPE], 'albums.example')).toEqual([])
    expect(filterJobs([SUMMER, WINTER], 'done')).toEqual([SUMMER, WINTER])
    expect(filterJobs([SUMMER, WINTER], 'failed')).toEqual([])
  })

  it('returns an empty list when nothing matches', () => {
    expect(filterJobs([SUMMER, WINTER], 'nope')).toEqual([])
    expect(matchesJobSearch(SUMMER, 'winter')).toBe(false)
  })
})
