import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeEventSource, JobEventBuilder } from '../testing/index.ts'
import { JobEventSource } from './events.ts'

function ingestEvent(overrides: Parameters<typeof JobEventBuilder.ingest>[0] = {}) {
  return JobEventBuilder.ingest({
    job_id: 'job-1',
    message: 'Reading files',
    current: 1,
    total: 3,
    occurred_at: undefined,
    ...overrides,
  }).build()
}

describe('JobEventSource', () => {
  beforeEach(() => {
    FakeEventSource.install()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('opens EventSource at /api/jobs/{id}/events', () => {
    const source = new JobEventSource()
    source.subscribe('job-42', vi.fn())

    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0]!.url).toBe('/api/jobs/job-42/events')
  })

  it('appends phase=publish when requested', () => {
    const source = new JobEventSource()
    source.subscribe('job-42', vi.fn(), 'publish')

    expect(FakeEventSource.instances[0]!.url).toBe('/api/jobs/job-42/events?phase=publish')
  })

  it('appends phase=history when requested', () => {
    const source = new JobEventSource()
    source.subscribe('job-42', vi.fn(), 'history')

    expect(FakeEventSource.instances[0]!.url).toBe('/api/jobs/job-42/events?phase=history')
  })

  it('appends phase=scrape when requested', () => {
    const source = new JobEventSource()
    source.subscribe('job-42', vi.fn(), 'scrape')

    expect(FakeEventSource.instances[0]!.url).toBe('/api/jobs/job-42/events?phase=scrape')
  })

  it('parses JSON message data and calls onEvent', () => {
    const onEvent = vi.fn()
    const source = new JobEventSource()
    source.subscribe('job-1', onEvent)

    const payload = ingestEvent()
    FakeEventSource.instances[0]!.emit(JSON.stringify(payload))

    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onEvent).toHaveBeenCalledWith(payload)
  })

  it('calls onEvent for each SSE message', () => {
    const onEvent = vi.fn()
    const source = new JobEventSource()
    source.subscribe('job-1', onEvent)
    const es = FakeEventSource.instances[0]!

    es.emit(JSON.stringify(ingestEvent({ stage: 'ingest', message: '', current: 0, total: 0 })))
    es.emit(
      JSON.stringify(ingestEvent({ stage: 'parse', message: 'Parsing', current: 1, total: 2 })),
    )
    es.emit(
      JSON.stringify(
        ingestEvent({
          stage: 'preview_ready',
          message: 'Ready',
          current: 2,
          total: 2,
          extra: { items: 5 },
        }),
      ),
    )
    es.emit(
      JSON.stringify(ingestEvent({ stage: 'error', message: 'Failed', current: 0, total: 0 })),
    )

    expect(onEvent).toHaveBeenCalledTimes(4)
    expect(onEvent.mock.calls[0]![0]).toMatchObject({ stage: 'ingest' })
    expect(onEvent.mock.calls[1]![0]).toMatchObject({ stage: 'parse' })
    expect(onEvent.mock.calls[2]![0]).toMatchObject({
      stage: 'preview_ready',
      extra: { items: 5 },
    })
    expect(onEvent.mock.calls[3]![0]).toMatchObject({ stage: 'error' })
  })

  it('unsubscribe closes the EventSource', () => {
    const source = new JobEventSource()
    const unsubscribe = source.subscribe('job-1', vi.fn())
    const es = FakeEventSource.instances[0]!

    expect(es.closed).toBe(false)
    unsubscribe()
    expect(es.closed).toBe(true)
  })

  it('does not call onEvent after unsubscribe', () => {
    const onEvent = vi.fn()
    const source = new JobEventSource()
    const unsubscribe = source.subscribe('job-1', onEvent)
    unsubscribe()

    FakeEventSource.instances[0]!.emit(JSON.stringify(ingestEvent({ stage: 'error' })))

    expect(onEvent).not.toHaveBeenCalled()
  })
})
