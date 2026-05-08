/**
 * SchedulerOverview — T1.5d.
 *
 * Renders a row of cards (one per scheduled job) backed by the unified
 * /api/scheduler/* job-status API and a detail modal with the last 20 runs.
 *
 * Lives inside the Jobs page (we extend the existing Jobs.tsx in-place rather
 * than spinning up a /scheduler route — see PR body for rationale).
 *
 * "Run now" UX:
 *  - POST /scheduler/jobs/{name}/run returns immediately with a tracking
 *    handle. We optimistically flip the badge to "running", invalidate the
 *    cached list, then poll listJobs every 1.5s for up to 5 minutes. The
 *    poll terminates as soon as the job's last_run_at advances past the
 *    timestamp we captured at trigger time.
 *  - We skip polling while the browser tab is hidden (visibilitychange) to
 *    avoid hammering the server when nobody is watching.
 *  - A small inline banner reports the outcome ("ran in 1.2s" / "failed: …")
 *    and can be dismissed.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Activity, AlertTriangle, CheckCircle2, ChevronRight, Clock, Loader2, Play, X } from 'lucide-react'
import {
  api,
  humanizeDuration,
  invalidateCache,
  timeAgo,
  timeUntil,
  type JobDetail,
  type JobRun,
  type JobSummary,
} from '../api'
import { Badge } from './Badge'
import { Modal } from './Modal'
import { Skeleton } from './Skeleton'

const POLL_INTERVAL_MS = 1500
const POLL_TIMEOUT_MS = 5 * 60_000

type RunOutcome = {
  job: string
  status: 'success' | 'failed' | 'queued'
  duration?: string
  error?: string
}

function statusVariant(status: string | null | undefined): string {
  if (!status) return 'default'
  if (status === 'success') return 'success'
  if (status === 'running' || status === 'queued') return 'info'
  if (status === 'failed' || status === 'error') return 'danger'
  return 'default'
}

function StatusBadge({ status }: { status: string | null | undefined }) {
  const { t } = useTranslation('jobs')
  const key = status || 'never'
  const label = t(`scheduler.status.${key}`, { defaultValue: status || t('scheduler.status.never') })
  return <Badge variant={statusVariant(status)}>{label}</Badge>
}

function BackendPill({ backend }: { backend: string }) {
  return (
    <span className="text-[10px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border border-[var(--border-default)] text-[var(--text-tertiary)]">
      {backend}
    </span>
  )
}

export function SchedulerOverview({ jobLabel }: { jobLabel: (name: string) => string }) {
  const { t } = useTranslation('jobs')
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [activeRuns, setActiveRuns] = useState<Set<string>>(new Set())
  const [outcome, setOutcome] = useState<RunOutcome | null>(null)
  const [detail, setDetail] = useState<JobDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [expandedRun, setExpandedRun] = useState<string | null>(null)

  // Hidden-tab guard for polling.
  const visibleRef = useRef(typeof document !== 'undefined' ? !document.hidden : true)
  useEffect(() => {
    const onVis = () => { visibleRef.current = !document.hidden }
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [])

  const refresh = useCallback(async () => {
    try {
      invalidateCache('/scheduler/jobs')
      const list = await api.scheduler.listJobs()
      setJobs(list)
    } catch {
      /* surface via banner if needed; silent for the periodic refresh */
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    api.scheduler.listJobs()
      .then((list) => setJobs(list))
      .catch(() => setJobs([]))
      .finally(() => setLoading(false))
  }, [])

  /** Poll until the job's last_run_at moves past `since` (or we time out). */
  const pollForCompletion = useCallback(async (name: string, since: number) => {
    const deadline = Date.now() + POLL_TIMEOUT_MS
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
      if (!visibleRef.current) continue
      try {
        invalidateCache('/scheduler/jobs')
        const list = await api.scheduler.listJobs()
        setJobs(list)
        const fresh = list.find((j) => j.name === name)
        if (!fresh) return null
        const lastTs = fresh.last_run_at ? new Date(fresh.last_run_at).getTime() : 0
        if (lastTs > since && fresh.last_status && fresh.last_status !== 'running') {
          return fresh
        }
      } catch {
        /* keep polling — transient errors are non-fatal */
      }
    }
    return null
  }, [])

  const handleRun = useCallback(async (job: JobSummary) => {
    if (activeRuns.has(job.name)) return
    setActiveRuns((s) => new Set(s).add(job.name))
    setOutcome(null)

    const sinceTs = job.last_run_at ? new Date(job.last_run_at).getTime() : 0
    // Optimistic: flip to running locally so the badge updates instantly.
    setJobs((prev) => prev.map((j) => (j.name === job.name ? { ...j, last_status: 'running' } : j)))

    try {
      const trigger = await api.scheduler.runJob(job.name)
      // Celery dispatch returns immediately ("queued"); show a banner so the
      // user knows we handed off, then keep polling for the eventual result.
      if (trigger.status === 'queued') {
        setOutcome({ job: job.name, status: 'queued' })
      }
      const final = await pollForCompletion(job.name, sinceTs)
      if (final) {
        if (final.last_status === 'success') {
          setOutcome({
            job: job.name,
            status: 'success',
            duration: humanizeDuration(final.last_duration_ms),
          })
        } else {
          setOutcome({
            job: job.name,
            status: 'failed',
            error: final.last_error || final.last_status || 'unknown',
          })
        }
      }
      // Invalidate the legacy /jobs cache too so the existing history table
      // picks up the new row when its parent reloads.
      invalidateCache('/jobs')
    } catch (e) {
      setOutcome({
        job: job.name,
        status: 'failed',
        error: e instanceof Error ? e.message : 'request failed',
      })
      await refresh()
    } finally {
      setActiveRuns((s) => {
        const n = new Set(s)
        n.delete(job.name)
        return n
      })
    }
  }, [activeRuns, pollForCompletion, refresh])

  const openDetail = useCallback(async (name: string) => {
    setDetailLoading(true)
    setExpandedRun(null)
    try {
      const d = await api.scheduler.getJob(name)
      setDetail(d)
    } catch {
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }, [])

  return (
    <section className="mb-6">
      <div className="flex justify-between items-baseline mb-3">
        <div>
          <h2 className="text-sm font-semibold">{t('scheduler.title')}</h2>
          <p className="text-xs text-[var(--text-tertiary)] mt-0.5">{t('scheduler.subtitle')}</p>
        </div>
      </div>

      {outcome && (
        <RunBanner outcome={outcome} jobLabel={jobLabel} onDismiss={() => setOutcome(null)} />
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {loading
          ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-44" />)
          : jobs.map((j) => (
              <SchedulerCard
                key={j.name}
                job={j}
                jobLabel={jobLabel}
                running={activeRuns.has(j.name)}
                onRun={() => handleRun(j)}
                onDetails={() => openDetail(j.name)}
              />
            ))}
        {!loading && jobs.length === 0 && (
          <div className="col-span-full text-xs text-[var(--text-tertiary)] py-6 text-center border border-dashed border-[var(--border-default)] rounded-xl">
            No scheduled jobs.
          </div>
        )}
      </div>

      <Modal
        open={!!detail || detailLoading}
        onClose={() => { setDetail(null); setExpandedRun(null) }}
        title={detail ? jobLabel(detail.name) : t('scheduler.detail.title')}
        maxWidth="max-w-3xl"
      >
        {detailLoading && !detail ? (
          <Skeleton className="h-40" />
        ) : detail ? (
          <DetailBody
            detail={detail}
            jobLabel={jobLabel}
            expandedRun={expandedRun}
            setExpandedRun={setExpandedRun}
          />
        ) : null}
      </Modal>
    </section>
  )
}

function SchedulerCard({
  job,
  jobLabel,
  running,
  onRun,
  onDetails,
}: {
  job: JobSummary
  jobLabel: (name: string) => string
  running: boolean
  onRun: () => void
  onDetails: () => void
}) {
  const { t } = useTranslation('jobs')
  const status = running ? 'running' : job.last_status
  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-4 flex flex-col gap-2 hover:shadow-md transition-all">
      <div className="flex justify-between items-start gap-2">
        <div className="min-w-0">
          <div className="text-sm font-medium truncate">{jobLabel(job.name)}</div>
          <div className="mt-1 flex items-center gap-1.5 flex-wrap">
            <StatusBadge status={status} />
            <BackendPill backend={job.backend} />
          </div>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-x-2 gap-y-1.5 text-[11px] mt-1">
        <dt className="text-[var(--text-tertiary)]">{t('scheduler.card.last_run')}</dt>
        <dd className="text-right text-[var(--text-secondary)] truncate">
          {timeAgo(job.last_run_at)}
        </dd>
        <dt className="text-[var(--text-tertiary)]">{t('scheduler.card.duration')}</dt>
        <dd className="text-right font-mono text-[var(--text-secondary)]">
          {humanizeDuration(job.last_duration_ms)}
        </dd>
        <dt className="text-[var(--text-tertiary)]">{t('scheduler.card.next_run')}</dt>
        <dd className="text-right text-[var(--text-secondary)] truncate">
          {timeUntil(job.next_run_at)}
        </dd>
      </dl>

      <div className="flex gap-2 mt-1">
        <button
          onClick={onRun}
          disabled={running}
          className="flex-1 flex items-center justify-center gap-1 px-2.5 py-1.5 text-xs bg-brand text-white rounded-md disabled:opacity-50"
        >
          {running ? (
            <><Loader2 size={12} className="animate-spin" /> {t('scheduler.trigger.running')}</>
          ) : (
            <><Play size={12} /> {t('job_card.actions.run_now')}</>
          )}
        </button>
        <button
          onClick={onDetails}
          className="flex items-center gap-1 px-2.5 py-1.5 text-xs border border-[var(--border-default)] rounded-md hover:bg-[var(--bg-secondary)]"
        >
          {t('scheduler.card.details')} <ChevronRight size={12} />
        </button>
      </div>
    </div>
  )
}

function RunBanner({
  outcome,
  jobLabel,
  onDismiss,
}: {
  outcome: RunOutcome
  jobLabel: (name: string) => string
  onDismiss: () => void
}) {
  const { t } = useTranslation('jobs')
  const icon = outcome.status === 'success'
    ? <CheckCircle2 size={14} className="text-[var(--success)]" />
    : outcome.status === 'failed'
      ? <AlertTriangle size={14} className="text-[var(--danger)]" />
      : <Activity size={14} className="text-brand" />
  const ring = outcome.status === 'success'
    ? 'border-[var(--success)] bg-[var(--success-subtle-bg)]'
    : outcome.status === 'failed'
      ? 'border-[var(--danger)] bg-[var(--danger-subtle-bg)]'
      : 'border-brand bg-[var(--brand-subtle-bg)]'
  const message = outcome.status === 'success'
    ? t('scheduler.trigger.success', {
        name: jobLabel(outcome.job),
        duration: outcome.duration ?? '',
      })
    : outcome.status === 'failed'
      ? t('scheduler.trigger.failed', {
          name: jobLabel(outcome.job),
          error: outcome.error ?? '',
        })
      : t('scheduler.trigger.queued', { name: jobLabel(outcome.job) })
  return (
    <div className={`flex items-center gap-2 px-3 py-2 mb-3 rounded-lg border ${ring} text-xs`}>
      {icon}
      <span className="flex-1 truncate">{message}</span>
      <button
        onClick={onDismiss}
        className="p-1 hover:bg-[var(--bg-secondary)] rounded text-[var(--text-tertiary)]"
        aria-label={t('scheduler.trigger.dismiss')}
      >
        <X size={12} />
      </button>
    </div>
  )
}

function DetailBody({
  detail,
  jobLabel,
  expandedRun,
  setExpandedRun,
}: {
  detail: JobDetail
  jobLabel: (name: string) => string
  expandedRun: string | null
  setExpandedRun: (id: string | null) => void
}) {
  const { t } = useTranslation('jobs')
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <StatusBadge status={detail.last_status} />
        <BackendPill backend={detail.backend} />
        <span className="text-xs text-[var(--text-tertiary)] font-mono flex items-center gap-1">
          <Clock size={12} /> {detail.cron}
        </span>
      </div>

      {detail.description && (
        <p className="text-xs text-[var(--text-secondary)]">{detail.description}</p>
      )}

      {detail.active_celery_task_ids.length > 0 && (
        <div className="border border-brand bg-[var(--brand-subtle-bg)] rounded-lg p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-brand mb-1">
            <span className="size-2 rounded-full bg-brand animate-pulse" />
            {t('scheduler.detail.live')} · {t('scheduler.detail.active_tasks')}
          </div>
          <ul className="text-[11px] font-mono text-[var(--text-secondary)] space-y-0.5">
            {detail.active_celery_task_ids.map((id) => (
              <li key={id}>{id}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <div className="text-xs font-semibold mb-2 flex items-center justify-between">
          <span>{t('scheduler.detail.recent_runs')} ({jobLabel(detail.name)})</span>
        </div>
        {detail.recent_runs.length === 0 ? (
          <p className="text-xs text-[var(--text-tertiary)] py-3">{t('scheduler.detail.no_runs')}</p>
        ) : (
          <div className="border border-[var(--border-subtle)] rounded-lg overflow-hidden">
            <table className="w-full text-[12px]">
              <thead className="bg-[var(--bg-secondary)] text-[var(--text-tertiary)] text-[11px]">
                <tr>
                  <th className="text-left py-1.5 px-2 font-medium">{t('scheduler.detail.started_at')}</th>
                  <th className="text-left py-1.5 px-2 font-medium">{t('scheduler.detail.finished_at')}</th>
                  <th className="text-left py-1.5 px-2 font-medium">{t('scheduler.detail.duration')}</th>
                  <th className="text-left py-1.5 px-2 font-medium">{t('scheduler.detail.status')}</th>
                  <th className="text-left py-1.5 px-2 font-medium">{t('scheduler.detail.error')}</th>
                </tr>
              </thead>
              <tbody>
                {detail.recent_runs.map((r) => (
                  <RunRow
                    key={r.id}
                    run={r}
                    expanded={expandedRun === r.id}
                    onToggle={() => setExpandedRun(expandedRun === r.id ? null : r.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function RunRow({
  run,
  expanded,
  onToggle,
}: {
  run: JobRun
  expanded: boolean
  onToggle: () => void
}) {
  const error = run.error_message
  return (
    <>
      <tr
        className={`border-t border-[var(--border-subtle)] cursor-pointer hover:bg-[var(--bg-secondary)] transition-colors ${expanded ? 'bg-[var(--bg-secondary)]' : ''}`}
        onClick={onToggle}
      >
        <td className="py-1.5 px-2 text-[var(--text-secondary)]">
          {run.started_at ? new Date(run.started_at).toLocaleString() : '-'}
        </td>
        <td className="py-1.5 px-2 text-[var(--text-secondary)]">
          {run.finished_at ? new Date(run.finished_at).toLocaleString() : '-'}
        </td>
        <td className="py-1.5 px-2 font-mono">
          {run.duration_seconds != null ? `${run.duration_seconds.toFixed(1)}s` : '-'}
        </td>
        <td className="py-1.5 px-2"><StatusBadge status={run.status} /></td>
        <td className="py-1.5 px-2 text-[var(--text-secondary)] max-w-[160px] truncate">
          {error || '-'}
        </td>
      </tr>
      {expanded && error && (
        <tr className="bg-[var(--bg-secondary)]">
          <td colSpan={5} className="py-2 px-3 text-[11px] font-mono whitespace-pre-wrap text-[var(--danger)]">
            {error}
          </td>
        </tr>
      )}
    </>
  )
}
