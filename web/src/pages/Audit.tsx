import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, invalidateCache, timeAgo } from '../api'
import { Badge } from '../components/Badge'
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
    <div>
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

      <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-5"><Skeleton className="h-48" /></div>
        ) : filtered.length === 0 ? (
          <p className="p-8 text-center text-[var(--text-tertiary)] text-sm">{t('empty')}</p>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)] bg-[var(--bg-secondary)]">
                <th className="text-left py-2 px-3 font-medium">{t('table.when')}</th>
                <th className="text-left py-2 px-3 font-medium">{t('table.feature')}</th>
                <th className="text-left py-2 px-3 font-medium">{t('table.changed_by')}</th>
                <th className="text-left py-2 px-3 font-medium">{t('table.type')}</th>
                <th className="text-left py-2 px-3 font-medium">{t('table.summary')}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((v, i) => (
                <tr
                  key={i}
                  className="border-b border-[var(--border-subtle)] hover:bg-[var(--bg-secondary)] cursor-pointer"
                  onClick={() => navigate(`/features/${encodeURIComponent(v.feature_name as string)}`)}
                >
                  <td className="py-2 px-3 text-[var(--text-tertiary)] whitespace-nowrap">
                    {v.created_at ? timeAgo(v.created_at as string) : '-'}
                  </td>
                  <td className="py-2 px-3 font-medium text-brand">{v.feature_name as string || '-'}</td>
                  <td className="py-2 px-3 text-[var(--text-secondary)]">{v.changed_by as string || '-'}</td>
                  <td className="py-2 px-3">
                    <Badge variant={TYPE_COLORS[v.change_type as string] || 'default'}>
                      {v.change_type as string}
                    </Badge>
                  </td>
                  <td className="py-2 px-3 text-[var(--text-secondary)] max-w-[300px] truncate">
                    {v.change_summary as string}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
