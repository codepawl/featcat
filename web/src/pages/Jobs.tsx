import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import { Badge } from '../components/Badge'
import { Card } from '../components/Card'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import { SchedulerOverview } from '../components/SchedulerOverview'

type JobLogRow = {
  job_name: string
  status: string
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  result_summary: unknown
  error_message: string | null
  triggered_by: string
}

type SortKey = 'started_desc' | 'started_asc' | 'duration_desc' | 'duration_asc'
const SORT_OPTIONS: readonly SortKey[] = ['started_desc', 'started_asc', 'duration_desc', 'duration_asc']

export function Jobs() {
  const { t } = useTranslation('jobs')
  const [logs, setLogs] = useState<JobLogRow[]>([])
  const [loading, setLoading] = useState(true)
  const [filterJob, setFilterJob] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [sort, setSort] = useState<SortKey>('started_desc')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [page, setPage] = useState(0)

  useEffect(() => {
    setLoading(true)
    api.jobs
      .logs({ limit: '500' })
      .then((l) => setLogs(Array.isArray(l) ? (l as JobLogRow[]) : []))
      .finally(() => setLoading(false))
  }, [])

  const filtered = logs
    .filter((l) => {
      if (filterJob && l.job_name !== filterJob) return false
      if (filterStatus && l.status !== filterStatus) return false
      return true
    })
    .slice()
    .sort((a, b) => {
      // null sorts last regardless of direction so blank rows don't anchor the
      // top of the list.
      if (sort === 'started_desc' || sort === 'started_asc') {
        const av = a.started_at ? new Date(a.started_at).getTime() : null
        const bv = b.started_at ? new Date(b.started_at).getTime() : null
        if (av === null && bv === null) return 0
        if (av === null) return 1
        if (bv === null) return -1
        return sort === 'started_desc' ? bv - av : av - bv
      }
      // duration
      const av = a.duration_seconds
      const bv = b.duration_seconds
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      return sort === 'duration_desc' ? bv - av : av - bv
    })
  const PAGE_SIZE = 50
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)

  // Job-name options for the history filter come from the log rows themselves —
  // avoids a second round-trip to /api/jobs now that SchedulerOverview owns
  // the canonical job list.
  const jobOptions = [...new Set(logs.map((l) => l.job_name).filter(Boolean))].sort()

  const getJobLabel = (jobName: string) => t(`job_names.${jobName}`, { defaultValue: jobName })

  return (
    <div>
      <PageHeader title={t('page.title')} size="compact" />

      <SchedulerOverview jobLabel={getJobLabel} />

      {/* Execution History */}
      <Card
        title={t('history.title')}
        actions={
          <>
            <select
              value={filterJob}
              onChange={(e) => {
                setFilterJob(e.target.value)
                setPage(0)
              }}
              className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-2.5 py-1.5 text-xs"
            >
              <option value="">{t('history.filters.all_jobs')}</option>
              {jobOptions.map((j) => (
                <option key={j} value={j}>{getJobLabel(j)}</option>
              ))}
            </select>
            <select
              value={filterStatus}
              onChange={(e) => {
                setFilterStatus(e.target.value)
                setPage(0)
              }}
              className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-2.5 py-1.5 text-xs"
            >
              <option value="">{t('history.filters.all_statuses')}</option>
              {['success', 'failed', 'warning', 'running'].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <select
              value={sort}
              onChange={(e) => {
                setSort(e.target.value as SortKey)
                setPage(0)
              }}
              className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-2.5 py-1.5 text-xs"
              aria-label={t('history.table.started')}
            >
              {SORT_OPTIONS.map((s) => (
                <option key={s} value={s}>{t(`history.filters.sort.${s}`)}</option>
              ))}
            </select>
          </>
        }
      >
        {loading ? <Skeleton className="h-40" /> : (
          <>
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
                  <th className="text-left py-2 font-medium">{t('history.table.job')}</th>
                  <th className="text-left py-2 font-medium">{t('history.table.status')}</th>
                  <th className="text-left py-2 font-medium">{t('history.table.started')}</th>
                  <th className="text-left py-2 font-medium">{t('history.table.duration')}</th>
                  <th className="text-left py-2 font-medium">{t('history.table.result')}</th>
                  <th className="text-left py-2 font-medium">{t('history.table.triggered_by')}</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((l, i) => (
                  <tr
                    key={i}
                    className="border-b border-[var(--border-subtle)] cursor-pointer hover:bg-[var(--bg-secondary)] transition-colors"
                    onClick={() => setExpanded(expanded === i ? null : i)}
                  >
                    <td className="py-2 font-medium">{getJobLabel(l.job_name)}</td>
                    <td className="py-2"><Badge variant={l.status}>{l.status}</Badge></td>
                    <td className="py-2 text-[var(--text-secondary)]">
                      {l.started_at ? new Date(l.started_at).toLocaleString() : '-'}
                    </td>
                    <td className="py-2 font-mono text-xs">
                      {l.duration_seconds != null ? `${l.duration_seconds.toFixed(1)}s` : '-'}
                    </td>
                    <td className="py-2 text-xs text-[var(--text-secondary)] max-w-[200px] truncate">
                      {typeof l.result_summary === 'string'
                        ? l.result_summary
                        : JSON.stringify(l.result_summary || '')}
                    </td>
                    <td className="py-2 text-xs text-[var(--text-tertiary)]">{l.triggered_by}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {expanded !== null && paged[expanded] && (
              <div className="mt-3 p-3 bg-[var(--bg-secondary)] rounded-lg text-xs font-mono animate-fade-in whitespace-pre-wrap">
                {JSON.stringify(paged[expanded].result_summary, null, 2)}
                {paged[expanded].error_message && (
                  <p className="text-[var(--danger)] mt-2">{paged[expanded].error_message}</p>
                )}
              </div>
            )}

            {totalPages > 1 && (
              <div className="flex gap-1 justify-center mt-4">
                <button
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                  className="px-3 py-1.5 text-xs rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] disabled:opacity-40"
                >
                  {t('actions.previous', { ns: 'common' })}
                </button>
                <span className="px-3 py-1.5 text-xs text-[var(--text-secondary)]">
                  {page + 1} / {totalPages}
                </span>
                <button
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage((p) => p + 1)}
                  className="px-3 py-1.5 text-xs rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] disabled:opacity-40"
                >
                  {t('actions.next', { ns: 'common' })}
                </button>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  )
}
