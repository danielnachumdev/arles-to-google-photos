import type { JobEvent } from './types.ts'

export type { JobEvent }

export type EventPhase = 'ingest' | 'publish' | 'history' | 'scrape'

export class JobEventSource {
  subscribe(
    jobId: string,
    onEvent: (event: JobEvent) => void,
    phase: EventPhase = 'ingest',
  ): () => void {
    const query = phase === 'ingest' ? '' : `?phase=${phase}`
    const source = new EventSource('/api/jobs/' + jobId + '/events' + query)
    const handler = (event: MessageEvent) => {
      onEvent(JSON.parse(event.data) as JobEvent)
    }
    source.addEventListener('message', handler)
    return () => {
      source.removeEventListener('message', handler)
      source.close()
    }
  }
}
