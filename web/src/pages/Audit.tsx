import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { RefreshCw } from 'lucide-react'
import { api, invalidateCache, timeAgo } from '../api'
import { Badge } from '../components/Badge'
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
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-xl font-semibold">{t('page.title')}</h1>
          <p className="text-sm text-[var(--text-tertiary)] mt-0.5">{t('page.subtitle')}</p>
        </div>
        <button onClick={load} disabled={loading} className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)] disabled:opacity-50">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> {t('actions.refresh', { ns: 'common' })}
        </button>
      </div>

      <div className="flex gap-3 items-center mb-4 flex-wrap">
        <select value={days} onChange={e => setDays(Number(e.target.value))}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px]">
          <option value={7}>{t('filters.last_n_days', { n: 7 })}</option>
          <option value={30}>{t('filters.last_n_days', { n: 30 })}</option>
          <option value={365}>{t('filters.all_time')}</option>
        </select>
        <select value={userFilter} onChange={e => setUserFilter(e.target.value)}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px]">
          <option value="">{t('filters.all_users')}</option>
          {users.map(u => <option key={u} value={u}>{u}</option>)}
        </select>
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px]">
          <option value="">{t('filters.all_types')}</option>
          <option value="doc">{t('change_types.doc')}</option>
          <option value="hints">{t('change_types.hints')}</option>
          <option value="definition">{t('change_types.definition')}</option>
          <option value="tags">{t('change_types.tags')}</option>
          <option value="metadata">{t('change_types.metadata')}</option>
        </select>
        <span className="text-xs text-[var(--text-tertiary)]">{t('filters.changes_count', { count: filtered.length })}</span>
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
                  <td className="py-2 px-3 font-medium text-accent">{v.feature_name as string || '-'}</td>
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
