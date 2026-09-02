import { JobBuilder, installXhrFetchBridge, jsonResponse } from '../testing/index.ts'
import { AlbumExistsError, MigrationClient } from './client.ts'
import type { Job, JobEdits, JobSummary } from './types.ts'

const SAMPLE_JOB: Job = JobBuilder.preview({
  id: 'job-1',
  import_origin: 'folder',
  folder_label: undefined,
  preview: {
    title: '2/8/2012 - mini fixture',
    description: 'A tiny album used in unit tests',
    multi_index: false,
    journal: null,
    items: [
      {
        id: '20120802_01',
        relpath: 'hrimages/20120802_01hr.JPG',
        caption: 'caption',
        size_bytes: 12,
        last_modified: '2012-08-02T10:00:00',
        taken_on: '2012-08-02',
      },
    ],
  },
}).build()

describe('MigrationClient', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let client: MigrationClient

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    installXhrFetchBridge(fetchMock)
    client = new MigrationClient()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  describe('createJob', () => {
    it('POSTs multipart files to /api/jobs using relpath as filename', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(SAMPLE_JOB, 201))

      const result = await client.createJob([
        { relpath: 'index.html', blob: new Blob(['<html></html>'], { type: 'text/html' }) },
        {
          relpath: 'hrimages/20120802_01hr.JPG',
          blob: new Blob([new Uint8Array([1, 2, 3])], { type: 'image/jpeg' }),
        },
      ])

      expect(result).toEqual(SAMPLE_JOB)
      expect(fetchMock).toHaveBeenCalledTimes(1)

      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs')
      expect(init.method).toBe('POST')
      expect(init.body).toBeInstanceOf(FormData)

      const form = init.body as FormData
      const uploaded = form.getAll('files')
      expect(uploaded).toHaveLength(2)
      expect(uploaded[0]).toBeInstanceOf(File)
      expect(uploaded[1]).toBeInstanceOf(File)
      expect((uploaded[0] as File).name).toBe('index.html')
      expect((uploaded[1] as File).name).toBe('hrimages/20120802_01hr.JPG')
      expect(form.getAll('lastModified')).toEqual([])
    })

    it('forwards upload progress from XHR', async () => {
      fetchMock.mockImplementationOnce(async () => jsonResponse(SAMPLE_JOB, 201))
      const progress: Array<{ loaded: number; total: number; percent: number }> = []
      await client.createJob([{ relpath: 'index.html', blob: new Blob(['x']) }], {
        onUploadProgress: (event) => progress.push(event),
      })
      expect(progress.length).toBeGreaterThan(0)
      expect(progress.at(-1)).toMatchObject({ percent: 100 })
    })

    it('appends lastModified ms values in the same order as files', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(SAMPLE_JOB, 201))

      await client.createJob([
        {
          relpath: 'index.html',
          blob: new Blob(['<html></html>']),
          lastModifiedMs: 1_700_000_000_000,
        },
        { relpath: 'hrimages/a.jpg', blob: new Blob([new Uint8Array([9])]) },
        {
          relpath: 'imagepages/a.html',
          blob: new Blob(['page']),
          lastModifiedMs: 0,
        },
      ])

      const form = (fetchMock.mock.calls[0] as [string, RequestInit])[1].body as FormData
      expect(form.getAll('lastModified')).toEqual(['1700000000000', '', '0'])
    })

    it('throws when create fails', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'invalid album' }, 400))

      await expect(
        client.createJob([{ relpath: 'index.html', blob: new Blob(['x']) }]),
      ).rejects.toThrow(/400/)
    })

    it('appends overwrite=true when requested', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(SAMPLE_JOB, 201))

      await client.createJob([{ relpath: 'index.html', blob: new Blob(['x']) }], {
        overwrite: true,
      })

      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs?overwrite=true')
      expect(init.method).toBe('POST')
    })

    it('sends auto_publish query and access_token form field', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(SAMPLE_JOB, 201))

      await client.createJob([{ relpath: 'index.html', blob: new Blob(['x']) }], {
        autoPublish: true,
        accessToken: 'ya29.tok',
      })

      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs?auto_publish=true')
      const form = init.body as FormData
      expect(form.get('access_token')).toBe('ya29.tok')
    })

    it('throws a generic 409 when the album_exists payload is missing', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'conflict' }, 409))
      await expect(
        client.createJob([{ relpath: 'index.html', blob: new Blob(['x']) }]),
      ).rejects.toThrow(/409/)
    })

    it('throws a generic 409 when the conflict body is not JSON', async () => {
      fetchMock.mockResolvedValueOnce(
        new Response('not-json', { status: 409, headers: { 'Content-Type': 'text/plain' } }),
      )
      await expect(
        client.createJob([{ relpath: 'index.html', blob: new Blob(['x']) }]),
      ).rejects.toThrow(/409/)
    })

    it('throws AlbumExistsError on 409 album_exists', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse(
          {
            detail: {
              code: 'album_exists',
              existing_id: 'job-x',
              title: 'Day 1',
            },
          },
          409,
        ),
      )

      try {
        await client.createJob([{ relpath: 'index.html', blob: new Blob(['x']) }])
        throw new Error('expected AlbumExistsError')
      } catch (err) {
        expect(err).toBeInstanceOf(AlbumExistsError)
        expect(err).toMatchObject({
          name: 'AlbumExistsError',
          existingId: 'job-x',
          title: 'Day 1',
        })
      }
    })

    it('throws ApiError payload_too_large on 413 HTML from the edge', async () => {
      fetchMock.mockResolvedValueOnce(
        new Response('<html><body>Request Entity Too Large</body></html>', {
          status: 413,
          headers: { 'Content-Type': 'text/html' },
        }),
      )
      try {
        await client.createJob([{ relpath: 'index.html', blob: new Blob(['x']) }])
        throw new Error('expected ApiError')
      } catch (err) {
        expect(err).toMatchObject({ name: 'ApiError', code: 'payload_too_large', status: 413 })
        expect((err as Error).message).not.toMatch(/<html/i)
      }
    })

    it('does not block large folders client-side (Cloud Run h2c raises the old 32 MiB cap)', async () => {
      const big = { size: 29 * 1024 * 1024 } as Blob
      fetchMock.mockResolvedValueOnce(
        jsonResponse(
          {
            id: 'job-big',
            status: 'pending',
            type: 'preview',
            error: null,
            product_url: null,
            preview: null,
          },
          201,
        ),
      )
      await expect(
        client.createJob([{ relpath: 'index.html', blob: big }]),
      ).resolves.toMatchObject({ id: 'job-big' })
      expect(fetchMock).toHaveBeenCalled()
    })
  })

  describe('createScrapeJob', () => {
    it('POSTs JSON url and headers to /api/jobs/scrape', async () => {
      const scrapeJob: Job = {
        id: 'scrape-1',
        status: 'running',
        type: 'scrape',
        error: null,
        product_url: null,
        preview: null,
        url: 'https://gallery.example/index.html',
      }
      fetchMock.mockResolvedValueOnce(jsonResponse(scrapeJob, 201))

      const result = await client.createScrapeJob({
        url: 'https://gallery.example/index.html',
        headers: { Authorization: 'Bearer test-token', 'X-Test-Header': 'fixture-value' },
      })

      expect(result).toEqual(scrapeJob)
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/scrape')
      expect(init.method).toBe('POST')
      expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
      expect(JSON.parse(String(init.body))).toEqual({
        url: 'https://gallery.example/index.html',
        headers: { Authorization: 'Bearer test-token', 'X-Test-Header': 'fixture-value' },
      })
    })

    it('includes auto_publish and access_token when requested', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse(
          {
            id: 'scrape-3',
            status: 'running',
            type: 'scrape',
            error: null,
            product_url: null,
            preview: null,
            url: 'https://gallery.example/',
          },
          201,
        ),
      )

      await client.createScrapeJob({
        url: 'https://gallery.example/',
        auto_publish: true,
        access_token: 'ya29.tok',
      })

      const init = fetchMock.mock.calls[0]![1] as RequestInit
      expect(JSON.parse(String(init.body))).toEqual({
        url: 'https://gallery.example/',
        auto_publish: true,
        access_token: 'ya29.tok',
      })
    })

    it('omits headers when none are provided', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse(
          {
            id: 'scrape-2',
            status: 'pending',
            type: 'scrape',
            error: null,
            product_url: null,
            preview: null,
            url: 'https://gallery.example/',
          },
          201,
        ),
      )

      await client.createScrapeJob({ url: 'https://gallery.example/' })

      const init = fetchMock.mock.calls[0]![1] as RequestInit
      expect(JSON.parse(String(init.body))).toEqual({ url: 'https://gallery.example/' })
    })

    it('throws when scrape create fails', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'bad url' }, 400))

      await expect(client.createScrapeJob({ url: 'https://gallery.example/' })).rejects.toThrow(
        /400/,
      )
    })
  })

  describe('listJobChildren', () => {
    it('GETs /api/jobs/:id/children and returns the children array', async () => {
      const children = [
        {
          id: 'preview-a',
          status: 'done' as const,
          type: 'preview' as const,
          title: 'Day 1',
          item_count: 2,
        },
      ]
      fetchMock.mockResolvedValueOnce(jsonResponse({ children }, 200))

      const result = await client.listJobChildren('scrape-1')

      expect(result).toEqual(children)
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/scrape-1/children')
      expect(init.method).toBe('GET')
    })

    it('accepts a bare children array payload', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse([{ id: 'child-1' }], 200))

      await expect(client.listJobChildren('scrape-1')).resolves.toEqual([{ id: 'child-1' }])
    })

    it('accepts a jobs array payload from the API', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ jobs: [{ id: 'child-1', status: 'running' }] }, 200))

      await expect(client.listJobChildren('scrape-1')).resolves.toEqual([
        { id: 'child-1', status: 'running' },
      ])
    })

    it('throws when children listing fails', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'job not found' }, 404))

      await expect(client.listJobChildren('nope')).rejects.toThrow(/404/)
    })
  })

  describe('getCancelPreview', () => {
    it('GETs /api/jobs/:id/cancel-preview and returns descendants', async () => {
      const descendants = [
        {
          id: 'preview-a',
          number: 12,
          status: 'pending' as const,
          type: 'preview' as const,
          title: 'Day 1',
        },
      ]
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ job: { id: 'scrape-1', status: 'running' }, descendants }, 200),
      )

      const result = await client.getCancelPreview('scrape-1')

      expect(result.descendants).toEqual(descendants)
      expect(result.job).toEqual({ id: 'scrape-1', status: 'running' })
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/scrape-1/cancel-preview')
      expect(init.method).toBe('GET')
    })

    it('returns an empty descendants list when the field is missing', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ job: { id: 'job-1' } }, 200))

      await expect(client.getCancelPreview('job-1')).resolves.toEqual({
        job: { id: 'job-1' },
        descendants: [],
      })
    })

    it('throws when cancel preview fails', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'job not found' }, 404))

      await expect(client.getCancelPreview('nope')).rejects.toThrow(/404/)
    })
  })

  describe('getRestartPreview', () => {
    it('GETs /api/jobs/:id/restart-preview and returns done vs remaining', async () => {
      const remaining = [
        {
          id: 'child-failed',
          number: 9,
          status: 'failed' as const,
          type: 'scrape' as const,
          scrape_url: 'https://albums.example/day2',
        },
      ]
      const done = [
        {
          id: 'child-done',
          number: 8,
          status: 'done' as const,
          type: 'scrape' as const,
          scrape_url: 'https://albums.example/day1',
        },
      ]
      fetchMock.mockResolvedValueOnce(
        jsonResponse(
          {
            job: { id: 'hub-1', status: 'cancelled' },
            descendants: [...done, ...remaining],
            done,
            remaining,
          },
          200,
        ),
      )

      const result = await client.getRestartPreview('hub-1')

      expect(result.descendants).toEqual([...done, ...remaining])
      expect(result.done).toEqual(done)
      expect(result.remaining).toEqual(remaining)
      expect(result.job).toEqual({ id: 'hub-1', status: 'cancelled' })
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/hub-1/restart-preview')
      expect(init.method).toBe('GET')
    })

    it('returns empty lists when fields are missing', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ job: { id: 'job-1' } }, 200))

      await expect(client.getRestartPreview('job-1')).resolves.toEqual({
        job: { id: 'job-1' },
        descendants: [],
        done: [],
        remaining: [],
      })
    })

    it('throws when restart preview fails', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'job not found' }, 404))

      await expect(client.getRestartPreview('nope')).rejects.toThrow(/404/)
    })
  })

  describe('listJobs', () => {
    it('GETs /api/jobs and returns the jobs array', async () => {
      const summaries: JobSummary[] = [
        {
          id: 'job-2',
          number: 2,
          status: 'done',
          type: 'upload',
          error: null,
          title: 'Newer album',
          item_count: 3,
          created_at: '2024-06-01T12:00:00+00:00',
          product_url: 'https://photos.example/album-2',
        },
        {
          id: 'job-1',
          number: 1,
          status: 'done',
          type: 'preview',
          error: null,
          title: 'Older album',
          item_count: 1,
          created_at: '2020-01-01T00:00:00+00:00',
          product_url: null,
        },
      ]
      fetchMock.mockResolvedValueOnce(jsonResponse({ jobs: summaries }, 200))

      const result = await client.listJobs()

      expect(result).toEqual(summaries)
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs')
      expect(init.method).toBe('GET')
    })

    it('GETs /api/jobs?dedupe=true when requested', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ jobs: [] }, 200))

      await client.listJobs({ dedupe: true })

      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs?dedupe=true')
      expect(init.method).toBe('GET')
    })

    it('throws when list fails', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'boom' }, 500))

      await expect(client.listJobs()).rejects.toThrow(/500/)
    })
  })

  describe('getJob', () => {
    it('GETs /api/jobs/:id and returns the job', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(SAMPLE_JOB, 200))

      const result = await client.getJob('job-1')

      expect(result).toEqual(SAMPLE_JOB)
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/job-1')
      expect(init.method).toBe('GET')
    })

    it('throws on missing job', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'job not found' }, 404))

      await expect(client.getJob('nope')).rejects.toThrow(/404/)
    })
  })

  describe('getJobHistory', () => {
    it('GETs /api/jobs/:id/history and returns events', async () => {
      const events = [
        {
          job_id: 'job-1',
          stage: 'ingest',
          message: 'Writing upload',
          current: 0,
          total: 1,
          extra: null,
          occurred_at: '2024-06-01T12:00:00+00:00',
        },
      ]
      fetchMock.mockResolvedValueOnce(jsonResponse({ events }, 200))

      const result = await client.getJobHistory('job-1')

      expect(result).toEqual(events)
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/job-1/history')
      expect(init.method).toBe('GET')
    })

    it('appends audience query when requested', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ events: [] }, 200))

      await client.getJobHistory('job-1', { audience: 'all' })

      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/job-1/history?audience=all')
      expect(init.method).toBe('GET')
    })

    it('throws on missing job', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'job not found' }, 404))

      await expect(client.getJobHistory('nope')).rejects.toThrow(/404/)
    })
  })

  describe('patchJob', () => {
    it('PATCHes JSON edits and returns the updated job', async () => {
      const edited: Job = {
        ...SAMPLE_JOB,
        preview: {
          ...SAMPLE_JOB.preview!,
          title: 'Edited title',
          items: [{ ...SAMPLE_JOB.preview!.items[0], caption: 'new caption' }],
        },
      }
      fetchMock.mockResolvedValueOnce(jsonResponse(edited, 200))

      const edits: JobEdits = {
        title: 'Edited title',
        captions: { '20120802_01': 'new caption' },
      }
      const result = await client.patchJob('job-1', edits)

      expect(result).toEqual(edited)
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/job-1')
      expect(init.method).toBe('PATCH')
      expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
      expect(init.body).toBe(JSON.stringify(edits))
    })

    it('throws when preview is not ready', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'preview not ready' }, 409))

      await expect(client.patchJob('job-1', { title: 'x' })).rejects.toThrow(/409/)
    })
  })

  describe('publishJob', () => {
    it('POSTs /api/jobs/:id/publish and returns the new upload job', async () => {
      const published: Job = {
        ...SAMPLE_JOB,
        id: 'upload-1',
        status: 'done',
        type: 'upload',
        product_url: 'https://photos.example/album-1',
        source_job_id: 'job-1',
      }
      fetchMock.mockResolvedValueOnce(jsonResponse(published, 201))

      const result = await client.publishJob('job-1', 'ya29.tok')

      expect(result).toEqual(published)
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/job-1/publish')
      expect(init.method).toBe('POST')
      expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
      expect(init.body).toBe(JSON.stringify({ access_token: 'ya29.tok' }))
    })

    it('throws when publish is rejected', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'publish already in progress' }, 409))

      await expect(client.publishJob('job-1', 'ya29.tok')).rejects.toThrow(/409/)
    })
  })

  describe('archiveJob', () => {
    it('POSTs /api/jobs/:id/archive and returns job plus archived ids', async () => {
      const archived: Job = { ...SAMPLE_JOB, archived_at: '2026-08-08T12:00:00+00:00' }
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ job: archived, archived_ids: ['job-1', 'job-child'] }, 200),
      )

      const result = await client.archiveJob('job-1')

      expect(result).toEqual({ job: archived, archived_ids: ['job-1', 'job-child'] })
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/job-1/archive')
      expect(init.method).toBe('POST')
    })

    it('throws when archive is rejected', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'job is still active' }, 409))

      await expect(client.archiveJob('job-1')).rejects.toThrow(/409/)
    })
  })

  describe('cancelJob', () => {
    it('POSTs /api/jobs/:id/cancel and returns the job', async () => {
      const cancelled: Job = { ...SAMPLE_JOB, status: 'cancelled' }
      fetchMock.mockResolvedValueOnce(jsonResponse(cancelled, 200))

      const result = await client.cancelJob('job-1')

      expect(result).toEqual(cancelled)
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/job-1/cancel')
      expect(init.method).toBe('POST')
    })

    it('throws when cancel is rejected', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'job already finished' }, 409))

      await expect(client.cancelJob('job-1')).rejects.toThrow(/409/)
    })
  })

  describe('deleteJob', () => {
    it('DELETEs /api/jobs/:id', async () => {
      fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))

      await client.deleteJob('job-1')

      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/job-1')
      expect(init.method).toBe('DELETE')
    })

    it('throws on missing job', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'job not found' }, 404))

      await expect(client.deleteJob('nope')).rejects.toThrow(/404/)
    })
  })

  describe('restartJob', () => {
    it('POSTs /api/jobs/:id/restart and returns the new job', async () => {
      const created: Job = {
        ...SAMPLE_JOB,
        id: 'job-2',
        status: 'pending',
        type: 'scrape',
      }
      fetchMock.mockResolvedValueOnce(jsonResponse(created, 201))

      const result = await client.restartJob('job-1')

      expect(result).toEqual(created)
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/job-1/restart')
      expect(init.method).toBe('POST')
      expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
      expect(init.body).toBe(JSON.stringify({}))
    })

    it('includes access_token when restarting an upload', async () => {
      const created: Job = {
        ...SAMPLE_JOB,
        id: 'upload-2',
        status: 'pending',
        type: 'upload',
      }
      fetchMock.mockResolvedValueOnce(jsonResponse(created, 201))

      await client.restartJob('upload-1', { accessToken: 'ya29.tok' })

      const init = fetchMock.mock.calls[0]![1] as RequestInit
      expect(JSON.parse(String(init.body))).toEqual({ access_token: 'ya29.tok' })
    })

    it('includes mode when restarting remaining children', async () => {
      const created: Job = {
        ...SAMPLE_JOB,
        id: 'job-2',
        status: 'pending',
        type: 'scrape',
      }
      fetchMock.mockResolvedValueOnce(jsonResponse(created, 201))

      await client.restartJob('hub-1', { mode: 'remaining' })

      const init = fetchMock.mock.calls[0]![1] as RequestInit
      expect(JSON.parse(String(init.body))).toEqual({ mode: 'remaining' })
    })

    it('throws when restart is rejected', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'job is not cancelled' }, 409))

      await expect(client.restartJob('job-1')).rejects.toThrow(/409/)
    })
  })

  describe('reprocessJob', () => {
    it('POSTs /api/jobs/:id/reprocess and returns the job', async () => {
      const reprocessed: Job = {
        ...SAMPLE_JOB,
        status: 'done',
        type: 'preview',
        product_url: 'https://photos.example/album-1',
      }
      fetchMock.mockResolvedValueOnce(jsonResponse(reprocessed, 200))

      const result = await client.reprocessJob('job-1')

      expect(result).toEqual(reprocessed)
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/jobs/job-1/reprocess')
      expect(init.method).toBe('POST')
      expect(init.body).toBeUndefined()
    })

    it('sends mode and title_prefix when creating a new album', async () => {
      const created: Job = {
        ...SAMPLE_JOB,
        id: 'job-2',
        status: 'pending',
        type: 'preview',
      }
      fetchMock.mockResolvedValueOnce(jsonResponse(created, 200))

      await client.reprocessJob('job-1', { mode: 'new', titlePrefix: 'Reprocessed · ' })

      const init = fetchMock.mock.calls[0]![1] as RequestInit
      expect(JSON.parse(String(init.body))).toEqual({
        mode: 'new',
        title_prefix: 'Reprocessed · ',
      })
    })

    it('throws when reprocess is rejected', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'job not found' }, 404))

      await expect(client.reprocessJob('nope')).rejects.toThrow(/404/)
    })
  })

  describe('settings', () => {
    it('GETs /api/settings', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ max_concurrent_jobs: 3, pending: 4, running: 2, waiting: 1 }, 200),
      )

      const result = await client.getSettings()

      expect(result).toEqual({ max_concurrent_jobs: 3, pending: 4, running: 2, waiting: 1 })
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/settings')
      expect(init.method).toBe('GET')
    })

    it('PATCHes max_concurrent_jobs', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ max_concurrent_jobs: 5, pending: 1, running: 2, waiting: 0 }, 200),
      )

      const result = await client.patchSettings(5)

      expect(result.max_concurrent_jobs).toBe(5)
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/settings')
      expect(init.method).toBe('PATCH')
      expect(JSON.parse(String(init.body))).toEqual({ max_concurrent_jobs: 5 })
    })
  })

  describe('mediaUrl', () => {
    it('returns the relative media path for an item', () => {
      expect(client.mediaUrl('job-1', '20120802_01')).toBe(
        '/api/jobs/job-1/media/20120802_01',
      )
    })

    it('appends a variant query when requested', () => {
      expect(client.mediaUrl('job-1', '0512_1_06[1]', 'thumb')).toBe(
        '/api/jobs/job-1/media/0512_1_06%5B1%5D?variant=thumb',
      )
      expect(client.mediaUrl('job-1', 'clip01', 'play')).toBe(
        '/api/jobs/job-1/media/clip01?variant=play',
      )
      expect(client.mediaUrl('job-1', 'clip01', 'original')).toBe(
        '/api/jobs/job-1/media/clip01',
      )
    })
  })
})
