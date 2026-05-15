import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, invalidateCache, timeAgo } from '../api'
import { Badge } from '../components/Badge'
import { Card } from '../components/Card'
import { DataTable } from '../components/DataTable'
import { FilterCountChip, FilterSelect } from '../components/filters'
import { PageHeader } from '../components/PageHeader'
import { RefreshButton } from '../components/RefreshButton'
import { Skeleton } from '../components/Skeleton'

const TYPE_COLORS: Record<string, string> = {
  doc: 'info',
  hints: 'warning',
  tags: 'success',
  definition: 'critical',
  metadata: 'default',
}

export function Audit() {
  const { t } = useTranslation('audit')
  const navigate = useNavigate()
  const [versions, setVersions] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(7)
  const [typeFilter, setTypeFilter] = useState('')
  const [userFilter, setUserFilter] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    invalidateCache('/versions')
    api.versions.recent(100, days)
      .then(setVersions)
      .catch(() => setVersions([]))
      .finally(() => setLoading(false))
  }, [days])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 60s
  useEffect(() => {
    const interval = setInterval(load, 60_000)
    return () => clearInterval(interval)
  }, [load])

  const users = [...new Set(versions.map(v => v.changed_by as string).filter(Boolean))].sort()

  const filtered = versions.filter(v => {
    if (typeFilter && v.change_type !== typeFilter) return false
    if (userFilter && v.changed_by !== userFilter) return false
    return true
  })

  return (
    <div data-testid="audit-page">
      <PageHeader
        title={t('page.title')}
        subtitle={t('page.subtitle')}
        size="compact"
        actions={<RefreshButton onClick={load} loading={loading} />}
      />

      <div className="flex gap-3 items-center mb-4 flex-wrap">
        <FilterSelect
          ariaLabel={t('filters.last_n_days', { n: 7 })}
          value={String(days)}
          onChange={(v) => setDays(Number(v))}
          options={[
            { value: '7', label: t('filters.last_n_days', { n: 7 }) },
            { value: '30', label: t('filters.last_n_days', { n: 30 }) },
            { value: '365', label: t('filters.all_time') },
          ]}
        />
        <FilterSelect
          ariaLabel={t('filters.all_users')}
          value={userFilter}
          onChange={setUserFilter}
          options={[
            { value: '', label: t('filters.all_users') },
            ...users.map((u) => ({ value: u, label: u })),
          ]}
        />
        <FilterSelect
          ariaLabel={t('filters.all_types')}
          value={typeFilter}
          onChange={setTypeFilter}
          options={[
            { value: '', label: t('filters.all_types') },
            { value: 'doc', label: t('change_types.doc') },
            { value: 'hints', label: t('change_types.hints') },
            { value: 'definition', label: t('change_types.definition') },
            { value: 'tags', label: t('change_types.tags') },
            { value: 'metadata', label: t('change_types.metadata') },
          ]}
        />
        <FilterCountChip count={filtered.length} />
      </div>

      <Card padding={loading ? 'normal' : 'none'} className="overflow-hidden">
        {loading ? (
          <Skeleton className="h-48" />
        ) : filtered.length === 0 ? (
          <p className="p-8 text-center text-[var(--text-tertiary)] text-sm">{t('empty')}</p>
        ) : (
          <DataTable
            columns={[
              {
                key: 'created_at',
                label: t('table.when'),
                render: (r) => (
                  <span className="text-[var(--text-tertiary)] whitespace-nowrap">
                    {r.created_at ? timeAgo(r.created_at as string) : '-'}
                  </span>
                ),
              },
              {
                key: 'feature_name',
                label: t('table.feature'),
                render: (r) => (
                  <span className="font-medium text-brand">{(r.feature_name as string) || '-'}</span>
                ),
              },
              {
                key: 'changed_by',
                label: t('table.changed_by'),
                render: (r) => (
                  <span className="text-[var(--text-secondary)]">{(r.changed_by as string) || '-'}</span>
                ),
              },
              {
                key: 'change_type',
                label: t('table.type'),
                sortable: false,
                render: (r) => (
                  <Badge variant={TYPE_COLORS[r.change_type as string] || 'default'}>
                    {r.change_type as string}
                  </Badge>
                ),
              },
              {
                key: 'change_summary',
                label: t('table.summary'),
                sortable: false,
                render: (r) => (
                  <span className="text-[var(--text-secondary)] max-w-[300px] truncate inline-block">
                    {r.change_summary as string}
                  </span>
                ),
              },
            ]}
            data={filtered}
            onRowClick={(r) =>
              navigate(`/features/${encodeURIComponent(r.feature_name as string)}`)
            }
            pageSize={50}
          />
        )}
      </Card>
    </div>
  )
}
