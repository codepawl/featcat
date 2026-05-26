import { useCallback, useEffect, useState } from 'react'
import { Play, Power } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api, invalidateCache, type MaterializationSchedule, type MaterializationScheduleRunResult } from '../api'
import { Alert } from '../components/Alert'
import { Badge } from '../components/Badge'
import { Card } from '../components/Card'
import { DataTable } from '../components/DataTable'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { RefreshButton } from '../components/RefreshButton'
import { Select } from '../components/Select'
import { Skeleton } from '../components/Skeleton'

type EnabledFilter = 'all' | 'enabled' | 'disabled'
type LimitOption = '20' | '50' | '100'

const ENABLED_OPTIONS: readonly EnabledFilter[] = ['all', 'enabled', 'disabled']
const LIMIT_OPTIONS: readonly LimitOption[] = ['20', '50', '100']

type ActionKind = 'toggle' | 'run'
type BusyAction = { scheduleId: string; kind: ActionKind } | null
type ActionError = { scheduleId: string; message: string } | null

function enabledParam(value: EnabledFilter): boolean | null {
  if (value === 'enabled') return true
  if (value === 'disabled') return false
  return null
}

function formatDate(value: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function TextCell({ value, strong = false }: { value: string | null; strong?: boolean }) {
  const text = value || '-'
  const color = value ? (strong ? 'text-[var(--text-primary)]' : 'text-[var(--text-secondary)]') : 'text-[var(--text-tertiary)]'
  return (
    <span title={text} className={`inline-block max-w-[170px] truncate ${strong ? 'font-medium' : ''} ${color}`}>
      {text}
    </span>
  )
}

function DateCell({ value }: { value: string | null }) {
  const text = formatDate(value)
  return (
    <span title={value || text} className="whitespace-nowrap text-[var(--text-secondary)]">
      {text}
    </span>
  )
}

function FeatureColumns({ columns }: { columns: string[] }) {
  const visible = columns.slice(0, 4)
  const remaining = columns.length - visible.length

  if (columns.length === 0) return <span className="text-[var(--text-tertiary)]">-</span>

  return (
    <span className="inline-flex max-w-[320px] flex-wrap items-center gap-1" title={columns.join(', ')}>
      {visible.map((column) => (
        <span
          key={column}
          className="max-w-[110px] truncate rounded bg-[var(--bg-tertiary)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--text-secondary)]"
        >
          {column}
        </span>
      ))}
      {remaining > 0 && <span className="text-[11px] text-[var(--text-tertiary)]">+{remaining}</span>}
    </span>
  )
}

function NamespaceCell({ project, featureView }: { project: string; featureView: string }) {
  const text = project || featureView ? `${project || '-'} / ${featureView || '-'}` : '-'
  return (
    <span title={text} className="inline-block max-w-[180px] truncate text-[var(--text-secondary)]">
      {text}
    </span>
  )
}

function runSummary(result: MaterializationScheduleRunResult): string {
  const parts: string[] = []
  if (result.status) parts.push(`status=${result.status}`)
  if (result.is_valid != null) parts.push(`is_valid=${result.is_valid}`)
  if (result.requested != null) parts.push(`requested=${result.requested}`)
  if (result.written != null) parts.push(`written=${result.written}`)
  if (result.skipped_older != null) parts.push(`skipped_older=${result.skipped_older}`)
  if (result.skipped_same_timestamp != null) parts.push(`skipped_same_timestamp=${result.skipped_same_timestamp}`)
  if (result.audit_id) parts.push(`audit=${result.audit_id}`)
  return parts.join(' ')
}

export function MaterializationSchedules() {
  const { t } = useTranslation('materializationSchedules')
  const [schedules, setSchedules] = useState<MaterializationSchedule[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [enabled, setEnabled] = useState<EnabledFilter>('all')
  const [limit, setLimit] = useState<LimitOption>('20')
  const [busyAction, setBusyAction] = useState<BusyAction>(null)
  const [actionError, setActionError] = useState<ActionError>(null)
  const [actionSummary, setActionSummary] = useState('')

  const load = useCallback((options?: { silent?: boolean }) => {
    if (!options?.silent) setLoading(true)
    setError('')
    invalidateCache('/online/materialization-schedules')
    api.online
      .materializationSchedules({ limit: Number(limit), enabled: enabledParam(enabled) })
      .then((rows) => setSchedules(Array.isArray(rows) ? rows : []))
      .catch((err) => {
        setSchedules([])
        setError(err instanceof Error ? err.message : t('error.description'))
      })
      .finally(() => {
        if (!options?.silent) setLoading(false)
      })
  }, [enabled, limit, t])

  const setScheduleEnabled = async (schedule: MaterializationSchedule, nextEnabled: boolean) => {
    setBusyAction({ scheduleId: schedule.id, kind: 'toggle' })
    setActionError(null)
    setActionSummary('')
    try {
      await api.online.updateMaterializationSchedule(schedule.id, { enabled: nextEnabled })
      await load({ silent: true })
    } catch (err) {
      setActionError({
        scheduleId: schedule.id,
        message: err instanceof Error ? err.message : t('actions.error'),
      })
    } finally {
      setBusyAction(null)
    }
  }

  const runSchedule = async (schedule: MaterializationSchedule) => {
    setBusyAction({ scheduleId: schedule.id, kind: 'run' })
    setActionError(null)
    setActionSummary('')
    try {
      const result = await api.online.runMaterializationSchedule(schedule.id)
      await load({ silent: true })
      const summary = runSummary(result)
      setActionSummary(
        summary
          ? t('actions.run_success', { name: schedule.name, summary })
          : t('actions.run_success_no_summary', { name: schedule.name }),
      )
    } catch (err) {
      setActionError({
        scheduleId: schedule.id,
        message: err instanceof Error ? err.message : t('actions.error'),
      })
    } finally {
      setBusyAction(null)
    }
  }

  useEffect(() => {
    load()
  }, [load])

  return (
    <div data-testid="materialization-schedules-page">
      <PageHeader
        title={t('page.title')}
        subtitle={t('page.subtitle')}
        size="compact"
        actions={<RefreshButton onClick={load} loading={loading} />}
      />

      <Card
        title={t('table.title')}
        padding={loading || error || schedules.length === 0 ? 'normal' : 'none'}
        className="overflow-hidden"
        actions={
          <>
            <Select<EnabledFilter>
              value={enabled}
              onChange={setEnabled}
              ariaLabel={t('filters.enabled')}
              options={ENABLED_OPTIONS.map((value) => ({
                value,
                label: value === 'enabled' ? t('filters.enabled_option') : t(`filters.${value}`),
              }))}
            />
            <Select<LimitOption>
              value={limit}
              onChange={setLimit}
              ariaLabel={t('filters.limit')}
              options={LIMIT_OPTIONS.map((value) => ({
                value,
                label: t('filters.limit_value', { count: Number(value) }),
              }))}
            />
          </>
        }
      >
        {actionSummary && (
          <Alert
            severity="success"
            message={actionSummary}
            dismissible
            onDismiss={() => setActionSummary('')}
            className="m-3"
          />
        )}
        {loading ? (
          <Skeleton className="h-48" />
        ) : error ? (
          <EmptyState
            variant="error"
            title={t('error.title')}
            description={error}
            action={{ label: t('error.retry'), onClick: load }}
          />
        ) : schedules.length === 0 ? (
          <EmptyState title={t('empty.title')} description={t('empty.description')} />
        ) : (
          <DataTable
            data={schedules}
            pageSize={50}
            columns={[
              {
                key: 'name',
                label: t('columns.name'),
                render: (row) => <TextCell value={row.name} strong />,
              },
              {
                key: 'enabled',
                label: t('columns.enabled'),
                render: (row) => (
                  <Badge variant={row.enabled ? 'success' : 'default'}>
                    {row.enabled ? t('states.enabled') : t('states.disabled')}
                  </Badge>
                ),
              },
              {
                key: 'source_name',
                label: t('columns.source_name'),
                render: (row) => <TextCell value={row.source_name} strong />,
              },
              {
                key: 'feature_columns',
                label: t('columns.feature_columns'),
                sortable: false,
                render: (row) => <FeatureColumns columns={row.feature_columns} />,
              },
              {
                key: 'namespace',
                label: t('columns.namespace'),
                sortable: false,
                render: (row) => <NamespaceCell project={row.project} featureView={row.feature_view} />,
              },
              {
                key: 'interval_seconds',
                label: t('columns.interval_seconds'),
                render: (row) => <span className="font-mono text-xs">{row.interval_seconds}</span>,
              },
              {
                key: 'last_run_at',
                label: t('columns.last_run_at'),
                render: (row) => <DateCell value={row.last_run_at} />,
              },
              {
                key: 'next_run_at',
                label: t('columns.next_run_at'),
                render: (row) => <DateCell value={row.next_run_at} />,
              },
              {
                key: 'lease_owner',
                label: t('columns.lease_owner'),
                render: (row) => <TextCell value={row.lease_owner} />,
              },
              {
                key: 'lease_until',
                label: t('columns.lease_until'),
                render: (row) => <DateCell value={row.lease_until} />,
              },
              {
                key: 'created_at',
                label: t('columns.created_at'),
                render: (row) => <DateCell value={row.created_at} />,
              },
              {
                key: 'updated_at',
                label: t('columns.updated_at'),
                render: (row) => <DateCell value={row.updated_at} />,
              },
              {
                key: 'actions',
                label: t('columns.actions'),
                sortable: false,
                render: (row) => {
                  const toggleBusy = busyAction?.scheduleId === row.id && busyAction.kind === 'toggle'
                  const runBusy = busyAction?.scheduleId === row.id && busyAction.kind === 'run'
                  const disabled = busyAction !== null
                  const nextEnabled = !row.enabled
                  return (
                    <span className="flex min-w-[180px] flex-col gap-1.5">
                      <span className="inline-flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => setScheduleEnabled(row, nextEnabled)}
                          disabled={disabled}
                          className="inline-flex items-center gap-1 rounded-md border border-[var(--border-default)] px-2 py-1 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <Power size={12} strokeWidth={1.8} />
                          {toggleBusy
                            ? t(row.enabled ? 'actions.disabling' : 'actions.enabling')
                            : t(row.enabled ? 'actions.disable' : 'actions.enable')}
                        </button>
                        <button
                          type="button"
                          onClick={() => runSchedule(row)}
                          disabled={disabled}
                          className="inline-flex items-center gap-1 rounded-md bg-brand px-2 py-1 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <Play size={12} strokeWidth={1.8} />
                          {runBusy ? t('actions.running') : t('actions.run_now')}
                        </button>
                      </span>
                      {actionError?.scheduleId === row.id && (
                        <span className="max-w-[220px] text-xs text-[var(--danger)]">{actionError.message}</span>
                      )}
                    </span>
                  )
                },
              },
            ]}
          />
        )}
      </Card>
    </div>
  )
}
