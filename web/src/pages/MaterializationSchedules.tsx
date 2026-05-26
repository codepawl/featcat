import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, invalidateCache, type MaterializationSchedule } from '../api'
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

export function MaterializationSchedules() {
  const { t } = useTranslation('materializationSchedules')
  const [schedules, setSchedules] = useState<MaterializationSchedule[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [enabled, setEnabled] = useState<EnabledFilter>('all')
  const [limit, setLimit] = useState<LimitOption>('20')

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    invalidateCache('/online/materialization-schedules')
    api.online
      .materializationSchedules({ limit: Number(limit), enabled: enabledParam(enabled) })
      .then((rows) => setSchedules(Array.isArray(rows) ? rows : []))
      .catch((err) => {
        setSchedules([])
        setError(err instanceof Error ? err.message : t('error.description'))
      })
      .finally(() => setLoading(false))
  }, [enabled, limit, t])

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
            ]}
          />
        )}
      </Card>
    </div>
  )
}
