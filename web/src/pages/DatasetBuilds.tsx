import { useCallback, useEffect, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api, type DatasetBuildAudit, type DatasetBuildIssue, type DatasetBuildStatus, invalidateCache } from '../api'
import { Badge } from '../components/Badge'
import { Card } from '../components/Card'
import { DataTable } from '../components/DataTable'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { RefreshButton } from '../components/RefreshButton'
import { Select } from '../components/Select'
import { Skeleton } from '../components/Skeleton'

type StatusFilter = DatasetBuildStatus | ''
type LimitOption = '20' | '50' | '100'

const STATUS_OPTIONS: readonly StatusFilter[] = ['', 'success', 'validation_failed', 'error']
const LIMIT_OPTIONS: readonly LimitOption[] = ['20', '50', '100']

const STATUS_VARIANTS: Record<DatasetBuildStatus, string> = {
  success: 'success',
  validation_failed: 'warning',
  error: 'danger',
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function issueLabel(issue: DatasetBuildIssue): string {
  return issue.field ? `${issue.field}: ${issue.message}` : issue.message
}

function summarizeIssues(row: DatasetBuildAudit): string {
  const errors = row.errors ?? []
  const warnings = row.warnings ?? []
  const first = errors[0] ?? warnings[0]
  if (!first) return ''
  return issueLabel(first)
}

function PathCell({ value }: { value: string | null }) {
  const { t } = useTranslation(['datasetBuilds', 'common'])
  const [copied, setCopied] = useState(false)

  if (!value) return <span className="text-[var(--text-tertiary)]">-</span>

  const copy = async () => {
    try {
      await navigator.clipboard?.writeText(value)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1200)
    } catch {
      setCopied(false)
    }
  }

  return (
    <span className="inline-flex items-center gap-1.5 max-w-[220px]">
      <code
        title={value}
        className="min-w-0 truncate font-mono text-[11px] text-[var(--text-secondary)]"
      >
        {value}
      </code>
      <button
        type="button"
        onClick={copy}
        className="shrink-0 p-1 rounded text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]"
        aria-label={t('actions.copy_path')}
        title={t('actions.copy_path')}
      >
        {copied ? <Check size={12} strokeWidth={2} /> : <Copy size={12} strokeWidth={1.8} />}
      </button>
    </span>
  )
}

function FeatureColumns({ columns }: { columns: string[] }) {
  const visible = columns.slice(0, 3)
  const remaining = columns.length - visible.length

  if (columns.length === 0) return <span className="text-[var(--text-tertiary)]">-</span>

  return (
    <span className="inline-flex max-w-[260px] items-center gap-1 overflow-hidden" title={columns.join(', ')}>
      {visible.map((column) => (
        <span
          key={column}
          className="min-w-0 max-w-[90px] truncate rounded bg-[var(--bg-tertiary)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--text-secondary)]"
        >
          {column}
        </span>
      ))}
      {remaining > 0 && (
        <span className="shrink-0 text-[11px] text-[var(--text-tertiary)]">+{remaining}</span>
      )}
    </span>
  )
}

function IssueSummary({ row }: { row: DatasetBuildAudit }) {
  const { t } = useTranslation('datasetBuilds')
  const errors = row.errors?.length ?? 0
  const warnings = row.warnings?.length ?? 0
  const summary = summarizeIssues(row)

  if (errors === 0 && warnings === 0) {
    return <span className="text-[var(--text-tertiary)]">{t('issues.none')}</span>
  }

  return (
    <span className="flex min-w-[180px] max-w-[280px] flex-col gap-1">
      <span className="flex items-center gap-1.5">
        {errors > 0 && <Badge variant="danger">{t('issues.errors', { count: errors })}</Badge>}
        {warnings > 0 && <Badge variant="warning">{t('issues.warnings', { count: warnings })}</Badge>}
      </span>
      {summary && (
        <span className="truncate text-xs text-[var(--text-secondary)]" title={summary}>
          {summary}
        </span>
      )}
    </span>
  )
}

export function DatasetBuilds() {
  const { t } = useTranslation('datasetBuilds')
  const [builds, setBuilds] = useState<DatasetBuildAudit[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [status, setStatus] = useState<StatusFilter>('')
  const [limit, setLimit] = useState<LimitOption>('20')

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    invalidateCache('/datasets/builds')
    api.datasets
      .builds({ limit: Number(limit), status })
      .then((rows) => setBuilds(Array.isArray(rows) ? rows : []))
      .catch((err) => {
        setBuilds([])
        setError(err instanceof Error ? err.message : t('error.description'))
      })
      .finally(() => setLoading(false))
  }, [limit, status, t])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div data-testid="dataset-builds-page">
      <PageHeader
        title={t('page.title')}
        subtitle={t('page.subtitle')}
        size="compact"
        actions={<RefreshButton onClick={load} loading={loading} />}
      />

      <Card
        title={t('table.title')}
        padding={loading || error || builds.length === 0 ? 'normal' : 'none'}
        className="overflow-hidden"
        actions={
          <>
            <Select<StatusFilter>
              value={status}
              onChange={setStatus}
              ariaLabel={t('filters.status')}
              options={STATUS_OPTIONS.map((value) => ({
                value,
                label: value ? t(`statuses.${value}`) : t('filters.all'),
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
        ) : builds.length === 0 ? (
          <EmptyState
            title={t('empty.title')}
            description={t('empty.description')}
          />
        ) : (
          <DataTable
            data={builds}
            pageSize={50}
            columns={[
              {
                key: 'status',
                label: t('columns.status'),
                render: (row) => (
                  <Badge variant={STATUS_VARIANTS[row.status]}>{t(`statuses.${row.status}`)}</Badge>
                ),
              },
              {
                key: 'created_at',
                label: t('columns.created_at'),
                render: (row) => (
                  <span className="whitespace-nowrap text-[var(--text-secondary)]">
                    {formatDate(row.created_at)}
                  </span>
                ),
              },
              {
                key: 'entity_df_path',
                label: t('columns.entity_df_path'),
                sortable: false,
                render: (row) => <PathCell value={row.entity_df_path} />,
              },
              {
                key: 'source_path',
                label: t('columns.source'),
                sortable: false,
                render: (row) => row.source_name ? (
                  <span title={row.source_path ?? row.source_name} className="inline-block max-w-[180px] truncate font-medium">
                    {row.source_name}
                  </span>
                ) : (
                  <PathCell value={row.source_path} />
                ),
              },
              {
                key: 'output_path',
                label: t('columns.output_path'),
                sortable: false,
                render: (row) => <PathCell value={row.output_path} />,
              },
              {
                key: 'row_count',
                label: t('columns.row_count'),
                render: (row) => <span className="font-mono text-xs">{row.row_count}</span>,
              },
              {
                key: 'feature_count',
                label: t('columns.feature_count'),
                render: (row) => <span className="font-mono text-xs">{row.feature_count}</span>,
              },
              {
                key: 'unresolved_row_count',
                label: t('columns.unresolved_row_count'),
                render: (row) => <span className="font-mono text-xs">{row.unresolved_row_count}</span>,
              },
              {
                key: 'missing_feature_value_count',
                label: t('columns.missing_feature_value_count'),
                render: (row) => <span className="font-mono text-xs">{row.missing_feature_value_count}</span>,
              },
              {
                key: 'feature_columns',
                label: t('columns.feature_columns'),
                sortable: false,
                render: (row) => <FeatureColumns columns={row.feature_columns} />,
              },
              {
                key: 'issues',
                label: t('columns.issues'),
                sortable: false,
                render: (row) => <IssueSummary row={row} />,
              },
            ]}
          />
        )}
      </Card>
    </div>
  )
}
