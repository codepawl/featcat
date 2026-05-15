import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api, invalidateCache } from '../api'

/**
 * Persists the active auto-doc batch job id in localStorage so a browser
 * reload mid-run does not lose the progress UI. On mount the banner reads the
 * stored id (if any), starts polling `/api/docs/generate-batch/<id>/status`,
 * and renders an inline progress chip. When the backend reports `done` or
 * `error`, or the job has been garbage-collected (404), the localStorage
 * entry is cleared and `onComplete` fires so the parent can refresh its data.
 *
 * Closes UAT finding "Auto-generate progress lost on F5/reload mid-batch"
 * from docs/BACKLOG.md (drift bug #1).
 */

export const ACTIVE_JOB_KEY = 'featcat:autodoc:active_job'

export type ActiveBatchJob = {
  jobId: string
  total: number
}

export function readActiveJob(): ActiveBatchJob | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem(ACTIVE_JOB_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<ActiveBatchJob>
    if (typeof parsed.jobId === 'string' && typeof parsed.total === 'number') {
      return { jobId: parsed.jobId, total: parsed.total }
    }
  } catch {
    /* fall through */
  }
  return null
}

export function writeActiveJob(job: ActiveBatchJob | null): void {
  if (typeof window === 'undefined') return
  if (job === null) {
    window.localStorage.removeItem(ACTIVE_JOB_KEY)
    return
  }
  window.localStorage.setItem(ACTIVE_JOB_KEY, JSON.stringify(job))
}

type Props = {
  /** External signal to seed the banner; null means idle. The banner also
   *  seeds itself from localStorage on first mount, so reload survives even
   *  if the parent has not re-supplied this prop yet. */
  job: ActiveBatchJob | null
  /** Called when the backend reports terminal state (done / error / 404). */
  onComplete: () => void
  /** Polling interval in milliseconds. Default 2000; lower in tests. */
  pollMs?: number
}

export function BatchProgressBanner({ job, onComplete, pollMs = 2000 }: Props) {
  // Seed from localStorage on first render so the user sees progress
  // immediately after F5 — before the parent component has had a chance to
  // hydrate from any other source.
  const [activeJob, setActiveJob] = useState<ActiveBatchJob | null>(() => job ?? readActiveJob())
  const [done, setDone] = useState(0)
  const [total, setTotal] = useState(activeJob?.total ?? 0)

  // Keep the local activeJob mirror in sync with the prop. The prop is the
  // authoritative source whenever the parent supplies one; localStorage only
  // wins when the prop is null (i.e. fresh mount post-reload).
  useEffect(() => {
    if (job !== null) {
      setActiveJob(job)
      setTotal(job.total)
      setDone(0)
    }
  }, [job])

  // Persist whenever the local view changes.
  useEffect(() => {
    writeActiveJob(activeJob)
  }, [activeJob])

  // Poll while a job is active.
  useEffect(() => {
    if (!activeJob) return
    let cancelled = false

    const tick = async () => {
      try {
        const status = await api.docs.batchStatus(activeJob.jobId)
        if (cancelled) return
        setDone(status.completed + status.failed)
        setTotal(status.total)
        if (status.status === 'done' || status.status === 'error') {
          setActiveJob(null)
          invalidateCache('/features')
          invalidateCache('/docs')
          onComplete()
        }
      } catch {
        // Either the job id has expired (server restart, 404) or the network
        // hiccupped. Treat both as terminal — better to drop the stale id
        // than poll indefinitely.
        if (cancelled) return
        setActiveJob(null)
        onComplete()
      }
    }

    void tick()
    const handle = setInterval(tick, pollMs)
    return () => {
      cancelled = true
      clearInterval(handle)
    }
  }, [activeJob, pollMs, onComplete])

  if (!activeJob) return null

  return (
    <span
      role="status"
      aria-live="polite"
      data-testid="batch-progress-banner"
      className="inline-flex items-center gap-1.5"
    >
      <RefreshCw size={14} className="animate-spin" />
      Generating... ({done}/{total})
    </span>
  )
}
