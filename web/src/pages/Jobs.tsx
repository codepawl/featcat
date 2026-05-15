import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import { Badge } from '../components/Badge'
import { Card } from '../components/Card'
import { DataTable } from '../components/DataTable'
import { FloatingPanel } from '../components/FloatingPanel'
import { PageHeader } from '../components/PageHeader'
import { Select } from '../components/Select'
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
  // Selected row → opens FloatingPanel with run detail. Replaces the prior
  // bottom-docked inline panel so the UX matches Features detail.
  const [selectedRun, setSelectedRun] = useState<JobLogRow | null>(null)

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

  // Job-name options for the history filter come from the log rows themselves —
  // avoids a second round-trip to /api/jobs now that SchedulerOverview owns
  // the canonical job list.
  const jobOptions = [...new Set(logs.map((l) => l.job_name).filter(Boolean))].sort()

  const getJobLabel = (jobName: string) => t(`job_names.${jobName}`, { defaultValue: jobName })

  const summarizeResult = (raw: unknown): string => {
    if (typeof raw === 'string') return raw
    if (raw == null) return ''
    return JSON.stringify(raw)
  }

  return (
    <div>
      <PageHeader title={t('page.title')} size="compact" />

      <SchedulerOverview jobLabel={getJobLabel} />

      {/* Execution History */}
      <Card
        title={t('history.title')}
        actions={
          <>
            <Select<string>
              value={filterJob}
              onChange={setFilterJob}
              ariaLabel={t('history.filters.all_jobs')}
              options={[
                { value: '', label: t('history.filters.all_jobs') },
                ...jobOptions.map((j) => ({ value: j, label: getJobLabel(j) })),
              ]}
            />
            <Select<string>
              value={filterStatus}
              onChange={setFilterStatus}
              ariaLabel={t('history.filters.all_statuses')}
              options={[
                { value: '', label: t('history.filters.all_statuses') },
                ...['success', 'failed', 'warning', 'running'].map((s) => ({ value: s, label: s })),
              ]}
            />
            <Select<SortKey>
              value={sort}
              onChange={(v) => setSort(v)}
              ariaLabel={t('history.table.started')}
              options={SORT_OPTIONS.map((s) => ({
                value: s,
                label: t(`history.filters.sort.${s}`),
              }))}
            />
          </>
        }
      >
        {loading ? (
          <Skeleton className="h-40" />
        ) : (
          <DataTable
            columns={[
              {
                key: 'job_name',
                label: t('history.table.job'),
                render: (r) => <span className="font-medium">{getJobLabel(r.job_name)}</span>,
              },
              {
                key: 'status',
                label: t('history.table.status'),
                sortable: false,
                render: (r) => <Badge variant={r.status}>{r.status}</Badge>,
              },
              {
                key: 'started_at',
                label: t('history.table.started'),
                render: (r) => (
                  <span className="text-[var(--text-secondary)]">
                    {r.started_at ? new Date(r.started_at).toLocaleString() : '-'}
                  </span>
                ),
              },
              {
                key: 'duration_seconds',
                label: t('history.table.duration'),
                render: (r) => (
                  <span className="font-mono text-xs">
                    {r.duration_seconds != null ? `${r.duration_seconds.toFixed(1)}s` : '-'}
                  </span>
                ),
              },
              {
                key: 'result_summary',
                label: t('history.table.result'),
                sortable: false,
                render: (r) => (
                  <span className="text-xs text-[var(--text-secondary)] max-w-[200px] truncate inline-block">
                    {summarizeResult(r.result_summary)}
                  </span>
                ),
              },
              {
                key: 'triggered_by',
                label: t('history.table.triggered_by'),
                render: (r) => (
                  <span className="text-xs text-[var(--text-tertiary)]">{r.triggered_by}</span>
                ),
              },
            ]}
            data={filtered}
            onRowClick={(r) => setSelectedRun(r)}
            pageSize={50}
          />
        )}
      </Card>

      {selectedRun && (
        <FloatingPanel
          open={!!selectedRun}
          onClose={() => setSelectedRun(null)}
          title={getJobLabel(selectedRun.job_name)}
          subtitle={
            selectedRun.started_at
              ? new Date(selectedRun.started_at).toLocaleString()
              : undefined
          }
          headerActions={<Badge variant={selectedRun.status}>{selectedRun.status}</Badge>}
          size="large"
          data-testid="job-run-detail"
        >
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-y-2 gap-x-6 text-[13px] mb-4">
            <div>
              <dt className="text-[11px] uppercase tracking-wider text-[var(--text-tertiary)] mb-0.5">
                {t('history.table.duration')}
              </dt>
              <dd className="font-mono">
                {selectedRun.duration_seconds != null ? `${selectedRun.duration_seconds.toFixed(1)}s` : '-'}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wider text-[var(--text-tertiary)] mb-0.5">
                {t('history.table.triggered_by')}
              </dt>
              <dd>{selectedRun.triggered_by || '-'}</dd>
            </div>
          </dl>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-1">
            {t('history.table.result')}
          </h3>
          <pre className="p-3 bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-lg text-xs font-mono whitespace-pre-wrap">
            {typeof selectedRun.result_summary === 'string'
              ? selectedRun.result_summary
              : JSON.stringify(selectedRun.result_summary, null, 2)}
          </pre>
          {selectedRun.error_message && (
            <>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--danger)] mb-1 mt-4">
                Error
              </h3>
              <pre className="p-3 bg-[var(--danger-subtle-bg)] border border-[var(--danger)] rounded-lg text-xs font-mono whitespace-pre-wrap text-[var(--danger)]">
                {selectedRun.error_message}
              </pre>
            </>
          )}
        </FloatingPanel>
      )}
    </div>
  )
}
