import type { JobEvent } from '../api/types.ts'

export const LIFECYCLE_STAGES = new Set([
  'done',
  'error',
  'failed',
  'cancelled',
  'preview_ready',
  'child',
  'waiting',
])

const LOG_STAGES = new Set(['scrape', 'parse', 'publish', 'ingest', 'log'])

export function inferJobEventKind(event: Pick<JobEvent, 'stage' | 'kind'>): 'log' | 'lifecycle' {
  if (event.kind === 'lifecycle' || event.kind === 'progress') {
    return 'lifecycle'
  }
  if (event.kind === 'log') {
    return 'log'
  }
  if (LIFECYCLE_STAGES.has(event.stage)) {
    return 'lifecycle'
  }
  return 'log'
}

export function inferJobEventAudience(event: Pick<JobEvent, 'audience'>): 'ui' | 'ops' {
  return event.audience === 'ops' ? 'ops' : 'ui'
}

export function isLifecycleJobEvent(event: Pick<JobEvent, 'stage' | 'kind'>): boolean {
  return inferJobEventKind(event) === 'lifecycle'
}

export function isOpsJobEvent(event: Pick<JobEvent, 'audience' | 'kind' | 'stage'>): boolean {
  return inferJobEventAudience(event) === 'ops' && !isLifecycleJobEvent(event)
}

export function shouldShowJobLog(
  event: Pick<JobEvent, 'stage' | 'kind' | 'audience'>,
  showOps: boolean,
): boolean {
  if (isOpsJobEvent(event)) {
    return showOps
  }
  return true
}

export function jobLogMessage(
  event: Pick<JobEvent, 'stage' | 'message' | 'kind'>,
  lifecycleLabel: (stage: string) => string,
): string {
  const message = event.message.trim()
  if (message) {
    return message
  }
  if (isLifecycleJobEvent(event) || LOG_STAGES.has(event.stage) === false) {
    return lifecycleLabel(event.stage)
  }
  return event.stage
}

export function formatLogTime(iso: string | null | undefined, locale: string): string {
  if (!iso) {
    return ''
  }
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) {
    return ''
  }
  return parsed.toLocaleTimeString(locale, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export function jobLogTone(event: Pick<JobEvent, 'stage' | 'kind'>): 'error' | 'cancelled' | null {
  if (event.stage === 'error' || event.stage === 'failed') {
    return 'error'
  }
  if (event.stage === 'cancelled') {
    return 'cancelled'
  }
  return null
}
